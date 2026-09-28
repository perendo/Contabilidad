"""Reglas de cierre (SPEC-028 T012): calendario, bloqueo y habilitacion de reaperturas.

Modulo de reglas puras (sin escritura) que comparten US1, US2 y US3:

* `rango_periodo`: deriva `fecha_ini..fecha_fin` de un mes o trimestre a partir
  del ejercicio (research D2; el rango no se acepta del cliente).
* `validar_periodo_abierto`: doble proteccion del bloqueo (research D9) junto
  al trigger `chk_journal_entry_fecha_abierta`; la invoca el motor de asientos
  de SPEC-002.
* `validar_ejercicio_cerrado`: el ejercicio no admite cierre si `FiscalYear`
  esta cerrado o si existe un `CierreEjercicio` completado.
* `validar_reapertura_autorizada`: cruza las reglas de SPEC-010 (formulacion
  vigente), SPEC-019 (legalizacion vigente) y SPEC-023 (IS contabilizado y
  definitivo) que bloquean la reapertura.
"""

from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import TIPOS_CIERRE, JournalEntryTipo
from models.closing.cierre_ejercicio import CierreEjercicio, EstadoCierreEjercicio
from models.closing.periodo_cerrado import (
    ESTADOS_BLOQUEANTES,
    EstadoPeriodo,
    PeriodoCerrado,
    TipoPeriodo,
)
from services.closing.errores import ClosingError, error
from services.journal.entry_service import AsientoError

AÑO_MIN, AÑO_MAX = 2000, 2100
MESES_POR_TRIMESTRE = 3


def tipo_periodo_de(valor: TipoPeriodo | str) -> TipoPeriodo:
    """Coacciona el tipo de periodo a enum, con 422 si el valor no existe.

    Sin esta guardia, `TipoPeriodo("SEMANAL")` lanza `ValueError` y el endpoint
    responderia 500 en lugar del 422 `tipo_periodo_invalido` del contrato.
    """
    if isinstance(valor, TipoPeriodo):
        return valor
    try:
        return TipoPeriodo(str(valor).strip().upper())
    except ValueError:
        raise error(
            "tipo_periodo_invalido", f"Tipo de periodo no soportado: {valor!r}", 422
        ) from None


def rango_periodo(ejercicio: int, tipo: TipoPeriodo | str, periodo: int) -> tuple[date, date]:
    """Rango de fechas del periodo, derivado del calendario (research D2).

    `MES` acepta 1..12 y `TRIMESTRE` 1..4; cualquier otro valor es un error de
    negocio 422 (`periodo_invalido`), nunca un rango silencioso.
    """
    if not (AÑO_MIN <= ejercicio <= AÑO_MAX):
        raise error("ejercicio_invalido", f"Ejercicio {ejercicio} fuera de rango", 422)
    tipo_texto = tipo.value if isinstance(tipo, TipoPeriodo) else str(tipo).upper()
    if tipo_texto == TipoPeriodo.MES.value:
        maximo = 12
    elif tipo_texto == TipoPeriodo.TRIMESTRE.value:
        maximo = 4
    else:
        raise error("tipo_periodo_invalido", f"Tipo de periodo no soportado: {tipo!r}", 422)
    if not isinstance(periodo, int) or isinstance(periodo, bool) or not (1 <= periodo <= maximo):
        raise error(
            "periodo_invalido",
            f"El periodo {periodo!r} no es valido para el tipo {tipo_texto} (1..{maximo})",
            422,
        )
    if tipo_texto == TipoPeriodo.MES.value:
        ultimo = calendar.monthrange(ejercicio, periodo)[1]
        return date(ejercicio, periodo, 1), date(ejercicio, periodo, ultimo)
    mes_ini = (periodo - 1) * MESES_POR_TRIMESTRE + 1
    mes_fin = mes_ini + MESES_POR_TRIMESTRE - 1
    ultimo = calendar.monthrange(ejercicio, mes_fin)[1]
    return date(ejercicio, mes_ini, 1), date(ejercicio, mes_fin, ultimo)


def meses_del_periodo(tipo: TipoPeriodo | str, periodo: int) -> range:
    """Numeros de mes (1..12) que abarca el periodo."""
    tipo_texto = tipo.value if isinstance(tipo, TipoPeriodo) else str(tipo).upper()
    if tipo_texto == TipoPeriodo.MES.value:
        return range(periodo, periodo + 1)
    inicio = (periodo - 1) * MESES_POR_TRIMESTRE + 1
    return range(inicio, inicio + MESES_POR_TRIMESTRE)


def solapan(
    fecha_ini_a: date, fecha_fin_a: date, fecha_ini_b: date, fecha_fin_b: date
) -> bool:
    """True si los dos rangos inclusivos se solapan."""
    return fecha_ini_a <= fecha_fin_b and fecha_ini_b <= fecha_fin_a


async def periodos_bloqueantes(
    db: AsyncSession, empresa_id: int, fecha: date
) -> list[PeriodoCerrado]:
    """Periodos cerrados de la empresa que cubren `fecha` (constitucion III)."""
    filas = (
        await db.scalars(
            select(PeriodoCerrado)
            .where(
                PeriodoCerrado.empresa_id == empresa_id,
                PeriodoCerrado.estado.in_(sorted(ESTADOS_BLOQUEANTES)),
                PeriodoCerrado.fecha_ini <= fecha,
                PeriodoCerrado.fecha_fin >= fecha,
            )
            .order_by(PeriodoCerrado.fecha_ini)
        )
    ).all()
    return list(filas)


async def validar_periodo_abierto(
    db: AsyncSession,
    empresa_id: int,
    fecha: date,
    *,
    tipo: JournalEntryTipo | None = None,
) -> None:
    """Rechaza con 409 `periodo_cerrado` si `fecha` cae en un periodo bloqueado.

    `tipo` permite excepcion para los asientos del propio paquete de cierre
    (`REGULARIZACION`/`CIERRE`/`OPENING`): el cierre anual se fecha el ultimo
    dia del ejercicio, que por definicion pertenece al ultimo mes cerrado.
    """
    if tipo is not None and tipo in TIPOS_CIERRE:
        return
    bloqueantes = await periodos_bloqueantes(db, empresa_id, fecha)
    if not bloqueantes:
        return
    primero = bloqueantes[0]
    raise error(
        "periodo_cerrado",
        (
            f"La fecha {fecha.isoformat()} pertenece al periodo "
            f"{primero.tipo.value} {primero.periodo} de {primero.ejercicio}, "
            "cerrado para la empresa"
        ),
        409,
    )


async def validar_ejercicio_abierto(db: AsyncSession, empresa_id: int, ejercicio: int) -> None:
    """El ejercicio debe existir y no estar cerrado ni cerrado por SPEC-028."""
    if not (AÑO_MIN <= ejercicio <= AÑO_MAX):
        raise error("ejercicio_invalido", f"Ejercicio {ejercicio} fuera de rango", 422)
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio
        )
    )
    if fy is not None and fy.is_closed:
        raise error("ejercicio_cerrado", f"El ejercicio {ejercicio} esta cerrado", 409)
    cierre = await db.scalar(
        select(CierreEjercicio).where(
            CierreEjercicio.empresa_id == empresa_id,
            CierreEjercicio.ejercicio == ejercicio,
            CierreEjercicio.estado == EstadoCierreEjercicio.completado,
        )
    )
    if cierre is not None:
        raise error(
            "ejercicio_cerrado",
            f"El ejercicio {ejercicio} ya tiene un cierre anual completado",
            409,
        )


async def validar_ejercicio_cerrado(db: AsyncSession, empresa_id: int, ejercicio: int) -> None:
    """409 `ejercicio_abierto` si el ejercicio todavia admite contabilizacion."""
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio
        )
    )
    if fy is not None and fy.is_closed:
        return
    raise error(
        "ejercicio_abierto", f"El ejercicio {ejercicio} no esta cerrado", 409
    )


def _como_cierre(exc: ClosingError) -> AsientoError:
    """Traduce un `ClosingError` al tipo que espera el motor de SPEC-002."""
    return AsientoError(exc.code, exc.message)


async def validar_periodo_abierto_motor(
    db: AsyncSession, empresa_id: int, fecha: date, tipo: JournalEntryTipo
) -> None:
    """Envoltorio para el motor de SPEC-002: falla con `AsientoError` (400/409)."""
    try:
        await validar_periodo_abierto(db, empresa_id, fecha, tipo=tipo)
    except ClosingError as exc:
        raise _como_cierre(exc) from exc


async def ejercicio_formulado(db: AsyncSession, empresa_id: int, ejercicio: int) -> bool:
    """SPEC-010: hay una formulacion de cuentas anuales vigente."""
    from models.reporting.formulacion import (
        FormulacionCuentasAnuales,
        FormulacionEstado,
    )

    vigente = await db.scalar(
        select(FormulacionCuentasAnuales.id).where(
            FormulacionCuentasAnuales.empresa_id == empresa_id,
            FormulacionCuentasAnuales.ejercicio == ejercicio,
            FormulacionCuentasAnuales.estado == FormulacionEstado.formulada,
        )
    )
    return vigente is not None


async def ejercicio_legalizado(db: AsyncSession, empresa_id: int, ejercicio: int) -> bool:
    """SPEC-019: hay una legalizacion vigente (tambien bloquea el motor)."""
    from models.ngo.libros import Legalizacion

    legalizacion = await db.scalar(
        select(Legalizacion.id).where(
            Legalizacion.empresa_id == empresa_id,
            Legalizacion.ejercicio == ejercicio,
            Legalizacion.valido.is_(True),
        )
    )
    return legalizacion is not None


async def is_contabilizado(db: AsyncSession, empresa_id: int, ejercicio: int) -> bool:
    """SPEC-023: hay un calculo de IS contabilizado y definitivo."""
    from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS

    calculo = await db.scalar(
        select(CalculoIS.id).where(
            CalculoIS.empresa_id == empresa_id,
            CalculoIS.ejercicio == ejercicio,
            CalculoIS.estado == EstadoCalculoIS.contabilizado,
            CalculoIS.provisional.is_(False),
        )
    )
    return calculo is not None


async def validar_reapertura_autorizada(
    db: AsyncSession, empresa_id: int, ejercicio: int, nota_impacto: str | None
) -> None:
    """Reglas de SC-004/FR-003: nada de reabrir ejercicios sellados.

    - Ejercicio con cuentas anuales formuladas (SPEC-010) o legalizado
      (SPEC-019) -> 409 `ejercicio_legalizado`, siempre.
    - IS contabilizado y definitivo (SPEC-023) -> 409 `is_liquidado` salvo que
      la solicitud documente el impacto parcial con `nota_impacto`.
    """
    if await ejercicio_formulado(db, empresa_id, ejercicio) or await ejercicio_legalizado(
        db, empresa_id, ejercicio
    ):
        raise error(
            "ejercicio_legalizado",
            (
                f"El ejercicio {ejercicio} esta formulado o legalizado: "
                "no admite reapertura de periodos"
            ),
            409,
        )
    if await is_contabilizado(db, empresa_id, ejercicio) and not (
        nota_impacto and nota_impacto.strip()
    ):
        raise error(
            "is_liquidado",
            (
                f"El IS del ejercicio {ejercicio} ya esta contabilizado: "
                "la reapertura exige una nota de impacto"
            ),
            409,
        )


async def validar_motivo(motivo: str | None) -> str:
    """FR-006: justificacion obligatoria y no vacia (422 si falta)."""
    if motivo is None or not str(motivo).strip():
        raise error(
            "justificacion_requerida",
            "La reapertura exige una justificacion (motivo) no vacia",
            422,
        )
    return str(motivo).strip()


__all__ = [
    "AÑO_MAX",
    "AÑO_MIN",
    "MESES_POR_TRIMESTRE",
    "EstadoPeriodo",
    "ejercicio_formulado",
    "ejercicio_legalizado",
    "is_contabilizado",
    "meses_del_periodo",
    "periodos_bloqueantes",
    "rango_periodo",
    "solapan",
    "tipo_periodo_de",
    "validar_ejercicio_abierto",
    "validar_ejercicio_cerrado",
    "validar_motivo",
    "validar_periodo_abierto",
    "validar_periodo_abierto_motor",
    "validar_reapertura_autorizada",
]
