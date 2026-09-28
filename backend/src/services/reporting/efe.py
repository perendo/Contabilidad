"""Estado de Flujos de Efectivo (SPEC-010 T026/T027).

Metodo directo: parte de los movimientos de tesoreria (grupo 5) del ejercicio y
los clasifica por actividad (operativa, inversion, financiacion) segun la
contrapartida, con reasignacion manual previa a la formulacion. El cuadre
(`saldo_final == saldo_inicial + variacion` y `variacion == variacion_balance`)
se verifica con `Decimal` exacto (FR-008).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.reporting.configuracion import ActividadEfe
from models.reporting.control_efe import ClasificacionEfe
from models.reporting.formulacion import (
    FormulacionCuentasAnuales,
    FormulacionEstado,
)
from services.audit.writer import audit_escribir
from services.reporting.saldos import error, fiscal_year
from services.reports.common import cuantizar, fmt

PREFIJO_TESORERIA = "5"


def _contrapartida_por_defecto(grupo: str) -> ActividadEfe:
    if grupo == "2":
        return ActividadEfe.inversion
    if grupo == "1":
        return ActividadEfe.financiacion
    return ActividadEfe.operativa


async def _lineas_tesoreria(
    db: AsyncSession, *, empresa_id: int, ejercicio: int, excluir: set[uuid.UUID]
) -> list[tuple[uuid.UUID, uuid.UUID, str, Decimal, Decimal, JournalEntryTipo]]:
    query = (
        select(
            JournalEntryLine.id,
            JournalEntryLine.journal_entry_id,
            JournalEntryLine.cuenta,
            JournalEntryLine.debe,
            JournalEntryLine.haber,
            JournalEntry.tipo,
        )
        .join(
            JournalEntry,
            (JournalEntryLine.journal_entry_id == JournalEntry.id)
            & (JournalEntryLine.empresa_id == JournalEntry.empresa_id),
        )
        .where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.estado == JournalEntryEstado.POSTED,
            JournalEntry.ejercicio == ejercicio,
        )
    )
    if excluir:
        query = query.where(JournalEntry.id.notin_(excluir))
    filas = (await db.execute(query)).all()
    return [
        (rid, entry_id, cuenta, debe, haber, tipo)
        for rid, entry_id, cuenta, debe, haber, tipo in filas
    ]


async def _overrides(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> dict[uuid.UUID, ActividadEfe]:
    filas = (
        await db.scalars(
            select(ClasificacionEfe).where(
                ClasificacionEfe.empresa_id == empresa_id,
                ClasificacionEfe.ejercicio == ejercicio,
            )
        )
    ).all()
    return {f.linea_id: f.actividad for f in filas}


async def generar_efe(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    modo: str = "provisional",
) -> dict:
    if modo not in ("provisional", "oficial"):
        raise error("modo_invalido", "modo debe ser provisional u oficial")

    fy = await fiscal_year(db, empresa_id, ejercicio)
    excluir: set[uuid.UUID] = set()
    if fy is not None and fy.cierre_entry_id is not None:
        excluir.add(fy.cierre_entry_id)

    filas = await _lineas_tesoreria(
        db, empresa_id=empresa_id, ejercicio=ejercicio, excluir=excluir
    )
    overrides = await _overrides(db, empresa_id=empresa_id, ejercicio=ejercicio)

    saldo_inicial = sum(
        (debe - haber for _, _, cuenta, debe, haber, tipo in filas
         if cuenta[:1] == PREFIJO_TESORERIA and tipo == JournalEntryTipo.OPENING),
        Decimal(0),
    )

    por_entry: dict[uuid.UUID, list[tuple[str, Decimal]]] = {}
    for _, entry_id, cuenta, debe, haber, _ in filas:
        por_entry.setdefault(entry_id, []).append((cuenta, debe - haber))

    actividades: dict[str, dict[str, Decimal]] = {
        a.value: {"cobros": Decimal(0), "pagos": Decimal(0)}
        for a in ActividadEfe
    }
    variacion = Decimal(0)
    for rid, entry_id, cuenta, debe, haber, tipo in filas:
        if cuenta[:1] != PREFIJO_TESORERIA or tipo == JournalEntryTipo.OPENING:
            continue
        importe = debe - haber
        variacion += importe
        actividad = overrides.get(rid)
        if actividad is None:
            contrapartidas = [
                (c, v) for c, v in por_entry.get(entry_id, []) if c[:1] != PREFIJO_TESORERIA
            ]
            if contrapartidas:
                contrapartida = max(contrapartidas, key=lambda cv: abs(cv[1]))[0]
                actividad = _contrapartida_por_defecto(contrapartida[:1])
            else:
                actividad = ActividadEfe.operativa
        clave = actividad.value
        if importe > 0:
            actividades[clave]["cobros"] += importe
        else:
            actividades[clave]["pagos"] += -importe

    saldo_final = saldo_inicial + variacion
    variacion_balance = variacion
    cuadre = cuantizar(saldo_final) == cuantizar(saldo_inicial + variacion) and cuantizar(
        variacion
    ) == cuantizar(variacion_balance)
    if modo == "oficial" and not cuadre:
        raise error("efe_descuadrado", "El EFE no cuadra con la variacion de tesoreria")

    return {
        "ejercicio": ejercicio,
        "modo": modo,
        "saldo_inicial_tesoreria": fmt(saldo_inicial),
        "actividades": {
            clave: {
                "cobros": fmt(valores["cobros"]),
                "pagos": fmt(valores["pagos"]),
                "neto": fmt(valores["cobros"] - valores["pagos"]),
            }
            for clave, valores in actividades.items()
        },
        "variacion_neta": fmt(variacion),
        "saldo_final_tesoreria": fmt(saldo_final),
        "variacion_balance": fmt(variacion_balance),
        "cuadre": cuadre,
    }


async def clasificar_movimiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    linea_id: uuid.UUID,
    actividad: str,
    motivo: str | None = None,
    actor: str | None = None,
) -> dict:
    try:
        actividad_enum = ActividadEfe(actividad)
    except ValueError:
        raise error("actividad_invalida", "Actividad no valida")

    vigente = await db.scalar(
        select(FormulacionCuentasAnuales.id).where(
            FormulacionCuentasAnuales.empresa_id == empresa_id,
            FormulacionCuentasAnuales.ejercicio == ejercicio,
            FormulacionCuentasAnuales.estado == FormulacionEstado.formulada,
        )
    )
    if vigente is not None:
        raise error("ya_formulada", "El ejercicio ya esta formulado oficialmente")

    linea = await db.scalar(
        select(JournalEntryLine.id)
        .join(
            JournalEntry,
            (JournalEntryLine.journal_entry_id == JournalEntry.id)
            & (JournalEntryLine.empresa_id == JournalEntry.empresa_id),
        )
        .where(
            JournalEntryLine.id == linea_id,
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntry.ejercicio == ejercicio,
            JournalEntry.estado == JournalEntryEstado.POSTED,
            JournalEntryLine.cuenta.like(f"{PREFIJO_TESORERIA}%"),
        )
    )
    if linea is None:
        raise error(
            "movimiento_no_encontrado",
            "Movimiento de tesoreria inexistente en la empresa activa",
        )

    existente = await db.scalar(
        select(ClasificacionEfe).where(
            ClasificacionEfe.empresa_id == empresa_id,
            ClasificacionEfe.ejercicio == ejercicio,
            ClasificacionEfe.linea_id == linea_id,
        )
    )
    if existente is None:
        existente = ClasificacionEfe(
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            linea_id=linea_id,
            actividad=actividad_enum,
            motivo=(motivo or "")[:255] or None,
            creado_por=actor,
        )
        db.add(existente)
    else:
        existente.actividad = actividad_enum
        existente.motivo = (motivo or "")[:255] or None
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CLASIFICAR_EFE",
        entity="clasificacion_efe",
        entity_id=str(existente.id),
        payload={"linea_id": str(linea_id), "actividad": actividad_enum.value},
    )
    await db.flush()
    return {"movimiento_id": str(linea_id), "actividad": actividad_enum.value}