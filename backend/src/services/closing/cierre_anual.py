"""Cierre anual completo (SPEC-028 T031-T033, US2/FR-002, research D5).

Proceso atomico que valida que todos los periodos intermedios del ejercicio
esten cerrados, genera los asientos `REGULARIZACION` (6/7 -> 129) y `CIERRE`
(saldo de todas las cuentas), marca `FiscalYear.is_closed = True`, invoca la
apertura del siguiente ejercicio (SPEC-009) y registra el `CierreEjercicio`.

Los asientos se construyen a nivel ORM con `next_numero` (numeracion
correlativa, constitucion IV) y se validan con partida doble estricta **antes**
de persistir (constitucion I). Reintentar el cierre de un ejercicio ya cerrado
devuelve 409 `ejercicio_cerrado` sin generar duplicados.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.closing.cierre_ejercicio import CierreEjercicio, EstadoCierreEjercicio
from services.audit.writer import audit_escribir
from services.cashflow.utils import c4
from services.closing.errores import error
from services.closing.periodo import meses_cubiertos
from services.closing.reglas_cierre import validar_ejercicio_abierto
from services.journal.sequence import next_numero

CUENTA_PYG = "129"
SUBCUENTA_PYG = "1290"
GRUPOS_GESTION = ("6", "7")


async def _netos_por_cuenta(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> dict[str, Decimal]:
    """`S(debe - haber)` por codigo de los asientos POSTED del ejercicio."""
    filas = (
        await db.execute(
            select(JournalEntryLine.cuenta, JournalEntryLine.debe, JournalEntryLine.haber)
            .join(
                JournalEntry,
                (JournalEntry.id == JournalEntryLine.journal_entry_id)
                & (JournalEntry.empresa_id == JournalEntryLine.empresa_id),
            )
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.estado == JournalEntryEstado.POSTED,
                JournalEntry.ejercicio == ejercicio,
            )
        )
    ).all()
    netos: dict[str, Decimal] = {}
    for codigo, debe, haber in filas:
        netos[str(codigo)] = netos.get(str(codigo), Decimal(0)) + Decimal(
            str(debe or 0)
        ) - Decimal(str(haber or 0))
    return {codigo: c4(neto) for codigo, neto in netos.items() if neto != 0}


async def _ids_por_codigo(db: AsyncSession, empresa_id: int) -> dict[str, int]:
    return {
        str(codigo): int(ident)
        for codigo, ident in (
            await db.execute(
                select(AccountPlan.code, AccountPlan.id).where(
                    AccountPlan.tenant_id == empresa_id, AccountPlan.is_active.is_(True)
                )
            )
        ).all()
    }


async def _cuenta_pyg_apuntable(db: AsyncSession, empresa_id: int) -> int:
    """Subcuenta 1290 apuntable para la regularizacion (mismo criterio que SPEC-004)."""
    existente = await db.scalar(
        select(AccountPlan.id).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == SUBCUENTA_PYG,
            AccountPlan.is_active.is_(True),
        )
    )
    if existente is not None:
        return int(existente)
    padre = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == CUENTA_PYG,
            AccountPlan.is_active.is_(True),
        )
    )
    if padre is None:
        raise error(
            "cuenta_regularizacion_no_existe",
            f"La cuenta {CUENTA_PYG} no existe en el plan de la empresa",
            422,
        )
    sub = AccountPlan(
        tenant_id=empresa_id,
        code=SUBCUENTA_PYG,
        name="Perdidas y ganancias del ejercicio",
        parent_id=padre.id,
        level=4,
        is_active=True,
        is_selectable=True,
    )
    db.add(sub)
    await db.flush()
    return int(sub.id)


def _cuadrar_lineas(lineas: list[dict[str, Any]]) -> tuple[Decimal, Decimal]:
    """Suma de Debe/Haber en `Decimal`; el servicio valida la igualdad."""
    debe = c4(sum((c4(l["debe"]) for l in lineas), Decimal(0)))
    haber = c4(sum((c4(l["haber"]) for l in lineas), Decimal(0)))
    return debe, haber


async def _publicar(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    concepto: str,
    tipo: JournalEntryTipo,
    lineas: list[dict[str, Any]],
    actor: str | None,
    cierre_id: uuid.UUID | None = None,
) -> JournalEntry | None:
    """Publica un asiento POSTED e inmutable; `None` si no hay lineas."""
    if not lineas:
        return None
    debe, haber = _cuadrar_lineas(lineas)
    if debe != haber or debe <= 0:
        raise error(
            "asiento_desbalanceado",
            f"Asiento de cierre desbalanceado: Debe {debe:0.4f} != Haber {haber:0.4f}",
            422,
        )
    numero = await next_numero(db, empresa_id, ejercicio)
    entrada = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=tipo,
        concepto=concepto,
        estado=JournalEntryEstado.POSTED,
        numero_asiento=numero,
        referencia_cierre_id=cierre_id,
        created_by=actor,
    )
    entrada.id = uuid.uuid4()
    db.add(entrada)
    await db.flush()
    for numero_linea, linea in enumerate(lineas, start=1):
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=entrada.id,
                account_id=linea["account_id"],
                line_no=numero_linea,
                cuenta=linea["cuenta"],
                debe=c4(linea["debe"]),
                haber=c4(linea["haber"]),
                descripcion=linea.get("descripcion"),
            )
        )
    await db.flush()
    return entrada


async def calcular_regularizacion(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> tuple[list[dict[str, Any]], Decimal]:
    """Lineas del asiento `REGULARIZACION` y resultado del ejercicio (US2).

    Cada cuenta de gestion con saldo se salda contra 1290 con el signo
    contrario; el resultado es la suma de los saldos de grupos 6 y 7.
    """
    netos = await _netos_por_cuenta(db, empresa_id, ejercicio)
    gestion = {codigo: neto for codigo, neto in netos.items() if codigo[:1] in GRUPOS_GESTION}
    if not gestion:
        return [], Decimal(0)
    ids = await _ids_por_codigo(db, empresa_id)
    id_pyg = await _cuenta_pyg_apuntable(db, empresa_id)
    for codigo in gestion:
        if codigo not in ids:
            raise error(
                "cuenta_no_existe", f"La cuenta {codigo} no existe en el plan", 422
            )
    lineas: list[dict[str, Any]] = []
    for codigo in sorted(gestion):
        neto = gestion[codigo]
        if neto > 0:
            lineas.append(
                {
                    "account_id": id_pyg,
                    "cuenta": SUBCUENTA_PYG,
                    "debe": neto,
                    "haber": Decimal(0),
                    "descripcion": f"Regularizacion {codigo}",
                }
            )
            lineas.append(
                {
                    "account_id": ids[codigo],
                    "cuenta": codigo,
                    "debe": Decimal(0),
                    "haber": neto,
                    "descripcion": f"Regularizacion {codigo}",
                }
            )
        else:
            lineas.append(
                {
                    "account_id": ids[codigo],
                    "cuenta": codigo,
                    "debe": -neto,
                    "haber": Decimal(0),
                    "descripcion": f"Regularizacion {codigo}",
                }
            )
            lineas.append(
                {
                    "account_id": id_pyg,
                    "cuenta": SUBCUENTA_PYG,
                    "debe": Decimal(0),
                    "haber": -neto,
                    "descripcion": f"Regularizacion {codigo}",
                }
            )
    resultado = resultado_ejercicio(gestion)
    return lineas, resultado


def resultado_ejercicio(gestion: dict[str, Decimal]) -> Decimal:
    """Resultado contable con signo de beneficio: `ingresos - gastos`.

    Las cuentas del grupo 7 tienen saldo acreedor (`neto` negativo) y las del 6
    deudor (`neto` positivo), de modo que el resultado coincide con el saldo
    final de la 1290 tras la regularizacion (positivo = beneficio).
    """
    ingresos = c4(-sum((neto for codigo, neto in gestion.items() if codigo[:1] == "7"), Decimal(0)))
    gastos = c4(sum((neto for codigo, neto in gestion.items() if codigo[:1] == "6"), Decimal(0)))
    return c4(ingresos - gastos)


async def calcular_cierre_saldos(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> list[dict[str, Any]]:
    """Lineas del asiento `CIERRE`: saldo de todas las cuentas con movimiento."""
    netos = await _netos_por_cuenta(db, empresa_id, ejercicio)
    if not netos:
        return []
    ids = await _ids_por_codigo(db, empresa_id)
    lineas: list[dict[str, Any]] = []
    for codigo in sorted(netos):
        if codigo not in ids:
            raise error(
                "cuenta_no_existe", f"La cuenta {codigo} no existe en el plan", 422
            )
        neto = netos[codigo]
        # El saldo se anula por el lado contrario: un `neto` deudor genera
        # `debe = neto`, uno acreedor `haber = -neto`. Nunca hay un lado
        # negativo (constitucion I y CHECK XOR de `journal_entry_line`).
        lineas.append(
            {
                "account_id": ids[codigo],
                "cuenta": codigo,
                "debe": neto if neto > 0 else Decimal(0),
                "haber": Decimal(0) if neto > 0 else -neto,
                "descripcion": f"Cierre {codigo}",
            }
        )
    return lineas


async def _abrir_siguiente(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    actor: str | None,
) -> uuid.UUID | None:
    """Invoca la apertura de SPEC-009 para `ejercicio + 1` si esta definida.

    La ausencia del ejercicio destino no es un error: la apertura se genera
    cuando el ciclo lo permita (research D5 la marca como "si existe definido").
    SPEC-009 excluye del calculo patrimonial el asiento de cierre, de modo que
    la 1290 regularizada es la que aporta el resultado y el patrimonio cuadra.
    """
    from models.fiscal.ejercicio import EjercicioContable
    from services.cycle.apertura import generar_asiento_apertura
    from services.cycle.validacion_previa import CicloError

    existe = await db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio + 1
        )
    )
    existe_contable = await db.scalar(
        select(EjercicioContable.id).where(
            EjercicioContable.empresa_id == empresa_id,
            EjercicioContable.ejercicio == ejercicio + 1,
        )
    )
    if existe is None and existe_contable is None:
        return None
    try:
        resultado = await generar_asiento_apertura(
            db, empresa_id=empresa_id, ejercicio_destino=ejercicio + 1, actor=actor
        )
    except CicloError:
        return None
    return uuid.UUID(str(resultado["asiento_id"]))




async def generar_cierre_anual(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    actor: str | None = None,
    ip: str | None = None,
    abrir_siguiente: bool = True,
) -> dict[str, Any]:
    """Cierre anual completo: regularizacion + cierre + bloqueo + apertura."""
    await validar_ejercicio_abierto(db, empresa_id, ejercicio)
    fy = await _fiscal_year_bloqueado(db, empresa_id, ejercicio)
    await _exigir_periodos_cerrados(db, empresa_id, ejercicio)

    fecha_cierre = fy.date_end
    cierre_id = uuid.uuid4()
    lineas_reg, resultado = await calcular_regularizacion(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )
    regularizacion = await _publicar(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha_cierre,
        concepto=f"Regularizacion {ejercicio}",
        tipo=JournalEntryTipo.REGULARIZACION,
        lineas=lineas_reg,
        actor=actor,
        cierre_id=cierre_id,
    )
    lineas_cierre = await calcular_cierre_saldos(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )
    cierre = await _publicar(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha_cierre,
        concepto=f"Cierre {ejercicio}",
        tipo=JournalEntryTipo.CIERRE,
        lineas=lineas_cierre,
        actor=actor,
        cierre_id=cierre_id,
    )

    fy.is_closed = True
    fy.closed_at = datetime.now(timezone.utc)
    fy.regularizacion_entry_id = regularizacion.id if regularizacion is not None else None
    fy.cierre_entry_id = cierre.id if cierre is not None else None
    await db.flush()

    fila = CierreEjercicio(
        id=cierre_id,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        estado=EstadoCierreEjercicio.completado,
        fecha_cierre=fecha_cierre,
        resultado_ejercicio=resultado,
        asiento_regularizacion_id=regularizacion.id if regularizacion is not None else None,
        asiento_cierre_id=cierre.id if cierre is not None else None,
        cerrado_por=actor,
        cerrado_at=datetime.now(timezone.utc),
    )
    db.add(fila)
    await db.flush()

    apertura = (
        await _abrir_siguiente(
            db, empresa_id=empresa_id, ejercicio=ejercicio, actor=actor
        )
        if abrir_siguiente
        else None
    )
    if apertura is not None:
        fila.asiento_apertura_id = apertura
        await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CIERRE_ANUAL",
        entity="cierre_ejercicio",
        entity_id=str(fila.id),
        ip=ip,
        payload={
            "ejercicio": ejercicio,
            "resultado_ejercicio": f"{resultado:0.4f}",
            "asiento_regularizacion_id": (
                str(regularizacion.id) if regularizacion is not None else None
            ),
            "asiento_cierre_id": str(cierre.id) if cierre is not None else None,
            "asiento_apertura_id": str(apertura) if apertura is not None else None,
        },
    )
    await db.flush()
    return {
        "cierre": fila,
        "asiento_regularizacion": regularizacion,
        "asiento_cierre": cierre,
        "asiento_apertura_id": apertura,
        "resultado_ejercicio": resultado,
    }


async def _fiscal_year_bloqueado(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> FiscalYear:
    """`FiscalYear` del ejercicio bajo `SELECT ... FOR UPDATE` (constitucion IV).

    El bloqueo se toma **antes** de exigir los periodos cerrados para que dos
    cierres concurrentes del mismo ejercicio no puedan generar asientos
    duplicados, y para que un ejercicio inexistente se reporte como 404.
    """
    fy = await db.scalar(
        select(FiscalYear)
        .where(FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio)
        .with_for_update()
    )
    if fy is None:
        raise error(
            "ejercicio_no_encontrado", f"Ejercicio {ejercicio} inexistente en la empresa", 404
        )
    if fy.is_closed:
        raise error("ejercicio_cerrado", f"El ejercicio {ejercicio} ya esta cerrado", 409)
    return fy


async def _exigir_periodos_cerrados(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> None:
    """US2: el cierre anual exige los 12 meses cubiertos por un cierre (FR-002)."""
    cubiertos = await meses_cubiertos(db, empresa_id=empresa_id, ejercicio=ejercicio)
    faltan = sorted(set(range(1, 13)) - cubiertos)
    if faltan:
        nombres = ", ".join(str(mes) for mes in faltan)
        raise error(
            "periodos_intermedios_pendientes",
            f"El ejercicio {ejercicio} tiene periodos intermedios sin cerrar: {nombres}",
            409,
        )


async def obtener_cierre_anual(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> CierreEjercicio:
    """Detalle del cierre anual; 404 si no existe en la empresa activa."""
    fila = await db.scalar(
        select(CierreEjercicio).where(
            CierreEjercicio.empresa_id == empresa_id, CierreEjercicio.ejercicio == ejercicio
        )
    )
    if fila is None:
        raise error(
            "cierre_no_encontrado",
            f"El ejercicio {ejercicio} no tiene cierre anual registrado",
            404,
        )
    return fila


__all__ = [
    "CUENTA_PYG",
    "GRUPOS_GESTION",
    "SUBCUENTA_PYG",
    "calcular_cierre_saldos",
    "calcular_regularizacion",
    "generar_cierre_anual",
    "obtener_cierre_anual",
    "resultado_ejercicio",
]
