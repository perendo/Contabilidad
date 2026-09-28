"""Informe de Estado de Flujos de Efectivo (SPEC-027 US2, T025/T026).

Este EFE es **por cuenta** (research D4), a diferencia del de SPEC-010
(`clasificacion_efe`, que reparte cada apunte de tesoreria por su
contrapartida). Cada `LineaEFE` agrega el saldo del ejercicio de una cuenta del
plan y lo clasifica en un bloque (operativa / inversion / financiacion).

Cuadre (FR-004 / SC-003). Por partida doble (constitucion I),
`S(debe - haber)` de todas las cuentas del ejercicio es cero, luego:

    saldo_inicial  = S(grupo 5 de los asientos OPENING)
    variacion_neta = -S(cuentas no tesoreria de los asientos NO OPENING)
                   = S(grupo 5 de los asientos NO OPENING)
    saldo_final    = saldo_inicial + variacion_neta

Las cuentas del grupo 5 **no** generan linea: son las que derivan los saldos
(incluirlas duplicaria la variacion). Los asientos `OPENING` tampoco aportan
lineas: su efecto ya esta en `saldo_inicial`. `generar_efe` **verifica** el
cuadre contra la variacion real del grupo 5 en lugar de asumirlo, y marca
`cuadre = false` si divergen.

Cruce con la conciliacion (FR-005 / D5): si el ultimo extracto conciliado de
una cuenta de tesoreria no coincide con `saldo_final`, el informe se marca
`sin_conciliar` como **aviso** y se puede formular igualmente (Assumptions).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.treasury.efe import (
    BloqueEFE,
    EstadoInformeEFE,
    InformeEFE,
    LineaEFE,
)
from services.audit import registrar_auditoria
from services.cashflow.clasificacion_actividad import clasificar_bloque, es_bloque
from services.cashflow.errores import error
from services.cashflow.saldos import saldo_conciliacion
from services.cashflow.utils import c4, es_cuenta_tesoreria, fmt


async def leer_efe(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> dict[str, Any]:
    """EFE del ejercicio: el **snapshot formulado** si existe, si no el provisional.

    Un EFE formulado es un documento inmutable (constitucion II): leerlo debe
    devolver lo que quedo.formulado, incluida la clasificacion que el usuario
    overrideo, no un recalculo que podria diferir del texto firmado.
    """
    _validar_ejercicio(ejercicio)
    formulado = await informe_formulado(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )
    if formulado is None:
        return await generar_efe(db, empresa_id=empresa_id, ejercicio=ejercicio)

    lineas = (
        await db.scalars(
            select(LineaEFE)
            .where(
                LineaEFE.empresa_id == empresa_id, LineaEFE.informe_id == formulado.id
            )
            .order_by(LineaEFE.codigo_cuenta)
        )
    ).all()
    totales = {bloque.value: Decimal(0) for bloque in BloqueEFE}
    for linea in lineas:
        totales[linea.bloque.value] = c4(totales[linea.bloque.value] + linea.importe)
    return {
        "ejercicio": ejercicio,
        "saldo_inicial": c4(formulado.saldo_inicial),
        "variacion_neta": c4(formulado.variacion_neta),
        "saldo_final": c4(formulado.saldo_final),
        "variacion_tesoreria": c4(formulado.variacion_neta),
        "cuadre": bool(formulado.cuadre),
        "sin_conciliar": bool(formulado.sin_conciliar),
        "saldo_conciliacion": (
            c4(formulado.saldo_conciliacion)
            if formulado.saldo_conciliacion is not None
            else None
        ),
        "totales": totales,
        "lineas": [
            {
                "cuenta_id": linea.cuenta_id,
                "codigo_cuenta": linea.codigo_cuenta,
                "bloque": linea.bloque.value,
                "importe": c4(linea.importe),
                "override_usuario": bool(linea.override_usuario),
            }
            for linea in lineas
        ],
        "formulado": True,
        "informe_id": formulado.id,
        "formulado_por": formulado.formulado_por,
        "fecha_formulacion": formulado.fecha_formulacion,
    }


__all__ = [
    "AÑO_MAX",
    "AÑO_MIN",
    "formular_efe",
    "generar_efe",
    "informe_formulado",
    "leer_efe",
]
AÑO_MIN = 2000
AÑO_MAX = 2100

#: Etiqueta de la columna auxiliar que marca si la linea pertenece a un
#: asiento `OPENING` (y por tanto ya reflected en `saldo_inicial`).
_ES_APERTURA = JournalEntry.tipo == JournalEntryTipo.OPENING


def _validar_ejercicio(ejercicio: int) -> None:
    if not AÑO_MIN <= ejercicio <= AÑO_MAX:
        raise error("ejercicio_invalido", f"Ejercicio {ejercicio} fuera de rango", 422)


async def _movimientos_del_ejercicio(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> list[tuple[str, Decimal, Decimal, bool]]:
    """`(cuenta, debe, haber, es_apertura)` de los asientos POSTED del ejercicio.

    Excluye el asiento de cierre y el de regularizacion: saldan todas las
    cuentas de forma artificial y no describen los flujos del ejercicio (mismo
    criterio que `services/reporting/saldos.py`).
    """
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio
        )
    )
    consulta = (
        select(
            JournalEntryLine.cuenta,
            JournalEntryLine.debe,
            JournalEntryLine.haber,
            _ES_APERTURA.label("es_apertura"),
        )
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
    if fy is not None:
        if fy.cierre_entry_id is not None:
            consulta = consulta.where(JournalEntry.id != fy.cierre_entry_id)
        if fy.regularizacion_entry_id is not None:
            consulta = consulta.where(JournalEntry.id != fy.regularizacion_entry_id)
    return [
        (codigo, c4(debe), c4(haber), bool(apertura))
        for codigo, debe, haber, apertura in (await db.execute(consulta)).all()
    ]


async def _ids_de_cuentas(
    db: AsyncSession, *, empresa_id: int, codigos: list[str]
) -> dict[str, int]:
    """Codigo PGC -> `account_plan.id` de la empresa activa (FK de `LineaEFE`)."""
    if not codigos:
        return {}
    filas = (
        await db.execute(
            select(AccountPlan.code, AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id, AccountPlan.code.in_(codigos)
            )
        )
    ).all()
    return {codigo: int(ident) for codigo, ident in filas}


def _aplicar_overrides(
    lineas: list[dict[str, Any]], clasificaciones: list[dict[str, Any]] | None
) -> None:
    """Reclasifica cuentas por id segun el override del usuario (research D4).

    El override manda sobre la inferencia por grupo y queda marcado con
    `override_usuario = true` para su trazabilidad.
    """
    for override in clasificaciones or []:
        if not isinstance(override, dict):
            raise error(
                "clasificacion_invalida",
                "Cada clasificacion debe ser un objeto {cuenta_id, bloque}",
                422,
            )
        bloque = str(override.get("bloque") or "")
        if not es_bloque(bloque):
            raise error(
                "bloque_invalido",
                f"Bloque no soportado: {bloque!r}. Use operativa/inversion/financiacion",
                422,
            )
        try:
            cuenta_id = int(override["cuenta_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise error(
                "clasificacion_invalida",
                f"cuenta_id no valido: {override.get('cuenta_id')!r}",
                422,
            ) from exc
        for linea in lineas:
            if linea["cuenta_id"] == cuenta_id:
                linea["bloque"] = bloque
                linea["override_usuario"] = True
                break
        else:
            raise error(
                "cuenta_no_clasificable",
                f"La cuenta {cuenta_id} no tiene movimientos en el ejercicio",
                422,
            )


# --- US2 / T025: generacion del informe -------------------------------------


async def generar_efe(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    clasificaciones: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calcula el EFE del ejercicio con cuadre y cruce de conciliacion (T025).

    No persiste nada: es la vista provisional que consume
    `GET /api/v1/tesoreria/efe?ejercicio=`. `formular_efe` es la que fija el
    snapshot inmutable.
    """
    _validar_ejercicio(ejercicio)
    movimientos = await _movimientos_del_ejercicio(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )

    saldo_inicial = Decimal(0)
    variacion_tesoreria = Decimal(0)
    por_cuenta: dict[str, Decimal] = {}
    for codigo, debe, haber, es_apertura in movimientos:
        neto = c4(debe - haber)
        if es_cuenta_tesoreria(codigo):
            if es_apertura:
                saldo_inicial = c4(saldo_inicial + neto)
            else:
                variacion_tesoreria = c4(variacion_tesoreria + neto)
            continue
        if es_apertura:
            # El efecto del asiento de apertura ya esta en `saldo_inicial`.
            continue
        por_cuenta[codigo] = c4(por_cuenta.get(codigo, Decimal(0)) + neto)

    ids = await _ids_de_cuentas(db, empresa_id=empresa_id, codigos=sorted(por_cuenta))
    lineas: list[dict[str, Any]] = []
    for codigo in sorted(por_cuenta):
        cuenta_id = ids.get(codigo)
        if cuenta_id is None:
            # Movimiento contra una cuenta ausente del plan de la empresa: sin
            # su id no se puede fijar la FK de `LineaEFE`, asi que no se informa.
            continue
        lineas.append(
            {
                "cuenta_id": cuenta_id,
                "codigo_cuenta": codigo,
                "bloque": clasificar_bloque(codigo),
                "importe": c4(-por_cuenta[codigo]),
                "override_usuario": False,
            }
        )
    _aplicar_overrides(lineas, clasificaciones)

    totales = {bloque.value: Decimal(0) for bloque in BloqueEFE}
    for linea in lineas:
        totales[linea["bloque"]] = c4(totales[linea["bloque"]] + linea["importe"])
    variacion_neta = c4(sum(totales.values(), Decimal(0)))
    saldo_final = c4(saldo_inicial + variacion_neta)
    # Verificacion real del cuadre contra el diario, no una asuncion.
    cuadre = variacion_neta == c4(variacion_tesoreria)
    conciliado = await saldo_conciliacion(
        db, empresa_id=empresa_id, hasta_fecha=date(ejercicio, 12, 31)
    )
    sin_conciliar = conciliado is not None and c4(conciliado) != saldo_final
    return {
        "ejercicio": ejercicio,
        "saldo_inicial": c4(saldo_inicial),
        "variacion_neta": variacion_neta,
        "saldo_final": saldo_final,
        "variacion_tesoreria": c4(variacion_tesoreria),
        "cuadre": cuadre,
        "sin_conciliar": sin_conciliar,
        "saldo_conciliacion": conciliado,
        "totales": totales,
        "lineas": lineas,
        "formulado": False,
        "informe_id": None,
    }


# --- US2 / T026: formulacion (snapshot inmutable) ---------------------------


async def informe_formulado(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> InformeEFE | None:
    """Informe ya formulado del ejercicio en la empresa activa, o `None`."""
    return await db.scalar(
        select(InformeEFE).where(
            InformeEFE.empresa_id == empresa_id, InformeEFE.ejercicio == ejercicio
        )
    )


async def formular_efe(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    actor: str = "sistema",
    clasificaciones: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Formula el EFE: fija el snapshot `formulado`, inmutable (FR-004/T026).

    409 si el ejercicio esta cerrado (SPEC-004) o si el EFE ya se formulo; 422
    si el cuadre falla. El cruce con la conciliacion solo avisa
    (`sin_conciliar`), nunca bloquea (research D5).
    """
    _validar_ejercicio(ejercicio)
    if await informe_formulado(db, empresa_id=empresa_id, ejercicio=ejercicio) is not None:
        raise error(
            "efe_ya_formulado", f"El EFE del ejercicio {ejercicio} ya esta formulado", 409
        )
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio
        )
    )
    if fy is not None and fy.is_closed:
        raise error(
            "ejercicio_cerrado",
            f"El ejercicio {ejercicio} esta cerrado: el EFE ya no es formulable",
            409,
        )

    informe = await generar_efe(
        db, empresa_id=empresa_id, ejercicio=ejercicio, clasificaciones=clasificaciones
    )
    if not informe["cuadre"]:
        raise error(
            "efe_descuadrado",
            "El EFE no cuadra con la variacion real de la tesoreria del diario",
            422,
        )

    registro = InformeEFE(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        saldo_inicial=informe["saldo_inicial"],
        saldo_final=informe["saldo_final"],
        variacion_neta=informe["variacion_neta"],
        cuadre=True,
        sin_conciliar=informe["sin_conciliar"],
        saldo_conciliacion=informe["saldo_conciliacion"],
        estado=EstadoInformeEFE.formulado,
        formulado_por=actor,
        fecha_formulacion=datetime.now(timezone.utc),
    )
    db.add(registro)
    try:
        await db.flush()
    except IntegrityError as exc:  # pragma: no cover - carrera concurrente
        raise error(
            "efe_ya_formulado", f"El EFE del ejercicio {ejercicio} ya esta formulado", 409
        ) from exc
    for linea in informe["lineas"]:
        db.add(
            LineaEFE(
                empresa_id=empresa_id,
                informe_id=registro.id,
                bloque=BloqueEFE(linea["bloque"]),
                cuenta_id=linea["cuenta_id"],
                codigo_cuenta=linea["codigo_cuenta"],
                importe=linea["importe"],
                override_usuario=linea["override_usuario"],
            )
        )
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="EFE_FORMULADO",
        entidad="informe_efe",
        entidad_id=registro.id,
        payload={
            "ejercicio": ejercicio,
            "saldo_inicial": fmt(informe["saldo_inicial"]),
            "variacion_neta": fmt(informe["variacion_neta"]),
            "saldo_final": fmt(informe["saldo_final"]),
            "cuadre": True,
            "sin_conciliar": informe["sin_conciliar"],
            "n_lineas": len(informe["lineas"]),
            "overrides": sum(1 for linea in informe["lineas"] if linea["override_usuario"]),
        },
        usuario=actor,
    )
    return {
        "informe_id": registro.id,
        "estado": registro.estado.value,
        "cuadre": True,
        "sin_conciliar": informe["sin_conciliar"],
        "saldo_inicial": informe["saldo_inicial"],
        "variacion_neta": informe["variacion_neta"],
        "saldo_final": informe["saldo_final"],
        "totales": informe["totales"],
        "lineas": informe["lineas"],
    }
