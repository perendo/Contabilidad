"""Cierre atómico de ejercicio (SPEC-004 US3): regularización + cierre + bloqueo.

Todo ocurre con ``flush()`` dentro del boundary ACID del llamante: si
cualquier paso falla, el ejercicio permanece abierto y sin asientos nuevos.
Los asientos se construyen con el motor de SPEC-002 (numeración correlativa
del diario, tipo ``ADJUSTMENT``, estado ``POSTED`` inmutable).
"""

from __future__ import annotations

from datetime import datetime, timezone
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
from services.audit.writer import audit_escribir
from services.journal.entry_service import asentar, crear_borrador

CUENTA_PYG = "129"
SUBCUENTA_PYG = "1290"


class CierreError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _fiscal_year_bloqueado(
    db: AsyncSession, empresa_id: int, year: int
) -> FiscalYear:
    fy = await db.scalar(
        select(FiscalYear)
        .where(FiscalYear.empresa_id == empresa_id, FiscalYear.year == year)
        .with_for_update()
    )
    if fy is None:
        raise CierreError("ejercicio_no_encontrado", f"Ejercicio {year} inexistente")
    if fy.is_closed:
        raise CierreError("ejercicio_cerrado", f"Ejercicio {year} ya cerrado")
    return fy


async def _sin_borradores(db: AsyncSession, empresa_id: int, fy: FiscalYear) -> None:
    pendiente = await db.scalar(
        select(JournalEntry.id).where(
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.estado == JournalEntryEstado.DRAFT,
            JournalEntry.fecha >= fy.date_start,
            JournalEntry.fecha <= fy.date_end,
        )
    )
    if pendiente is not None:
        raise CierreError(
            "borradores_pendientes",
            "Existen borradores sin asentar en el rango del ejercicio",
        )


async def _netos_por_cuenta(
    db: AsyncSession, empresa_id: int, fy: FiscalYear
) -> dict[str, Decimal]:
    filas = (
        await db.execute(
            select(JournalEntryLine.cuenta, JournalEntryLine.debe, JournalEntryLine.haber)
            .join(
                JournalEntry,
                (JournalEntryLine.journal_entry_id == JournalEntry.id)
                & (JournalEntryLine.empresa_id == JournalEntry.empresa_id),
            )
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.estado == JournalEntryEstado.POSTED,
                JournalEntry.fecha >= fy.date_start,
                JournalEntry.fecha <= fy.date_end,
            )
        )
    ).all()
    netos: dict[str, Decimal] = {}
    for cuenta, debe, haber in filas:
        netos[cuenta] = netos.get(cuenta, Decimal(0)) + debe - haber
    return {codigo: neto for codigo, neto in netos.items() if neto != 0}


async def _ids_por_codigo(db: AsyncSession, empresa_id: int) -> dict[str, int]:
    return {
        code: ident
        for code, ident in (
            await db.execute(
                select(AccountPlan.code, AccountPlan.id).where(
                    AccountPlan.tenant_id == empresa_id,
                    AccountPlan.is_active.is_(True),
                )
            )
        ).all()
    }


async def _publicar(
    db: AsyncSession,
    *,
    empresa_id: int,
    fy: FiscalYear,
    concepto: str,
    lineas: list[dict[str, Any]],
    actor: str | None,
) -> JournalEntry:
    borrador = await crear_borrador(
        db, empresa_id=empresa_id, fecha=fy.date_end,
        concepto=concepto, lineas=lineas, actor=actor,
        tipo=JournalEntryTipo.ADJUSTMENT,
    )
    return await asentar(db, empresa_id=empresa_id, entry_id=borrador.id, actor=actor)


async def _cuenta_pyg_apuntable(db: AsyncSession, empresa_id: int) -> int:
    """Selectable P&L account for regularización.

    The motor only posts to selectable (level-4) accounts while the chart
    carries Pérdidas y ganancias at 129, so the close ensures the
    ``1290`` subaccount (rolls up into 129 at every level ≤ 3).
    """
    existente = await db.scalar(
        select(AccountPlan.id).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == SUBCUENTA_PYG,
            AccountPlan.is_active.is_(True),
        )
    )
    if existente is not None:
        return existente
    padre = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == CUENTA_PYG,
            AccountPlan.is_active.is_(True),
        )
    )
    if padre is None:
        raise CierreError(
            "cuenta_regularizacion_no_existe",
            "La cuenta 129 no existe en el plan de la empresa",
        )
    sub = AccountPlan(
        tenant_id=empresa_id,
        code=SUBCUENTA_PYG,
        name="Pérdidas y ganancias del ejercicio",
        parent_id=padre.id,
        level=4,
        is_active=True,
        is_selectable=True,
    )
    db.add(sub)
    await db.flush()
    return sub.id


async def _regularizar(
    db: AsyncSession, empresa_id: int, fy: FiscalYear, actor: str | None
) -> JournalEntry | None:
    netos = await _netos_por_cuenta(db, empresa_id, fy)
    gestion = {c: n for c, n in netos.items() if c[:1] in ("6", "7")}
    if not gestion:
        return None
    ids = await _ids_por_codigo(db, empresa_id)
    id_pyg = await _cuenta_pyg_apuntable(db, empresa_id)
    for codigo in gestion:
        if codigo not in ids:
            raise CierreError(
                "cuenta_no_existe", f"La cuenta {codigo} no existe en el plan"
            )
    lineas: list[dict[str, Any]] = []
    for codigo in sorted(gestion):
        neto = gestion[codigo]
        if neto > 0:
            lineas.append({"account_id": id_pyg, "debit": str(neto), "credit": "0"})
            lineas.append({"account_id": ids[codigo], "debit": "0", "credit": str(neto)})
        else:
            lineas.append({"account_id": ids[codigo], "debit": str(-neto), "credit": "0"})
            lineas.append({"account_id": id_pyg, "debit": "0", "credit": str(-neto)})
    return await _publicar(
        db, empresa_id=empresa_id, fy=fy,
        concepto=f"Regularización {fy.year}", lineas=lineas, actor=actor,
    )


async def _cerrar_saldos(
    db: AsyncSession, empresa_id: int, fy: FiscalYear, actor: str | None
) -> JournalEntry | None:
    netos = await _netos_por_cuenta(db, empresa_id, fy)
    if not netos:
        return None
    ids = await _ids_por_codigo(db, empresa_id)
    lineas: list[dict[str, Any]] = []
    for codigo in sorted(netos):
        if codigo not in ids:
            raise CierreError(
                "cuenta_no_existe", f"La cuenta {codigo} no existe en el plan"
            )
        neto = netos[codigo]
        if neto > 0:
            lineas.append({"account_id": ids[codigo], "debit": "0", "credit": str(neto)})
        else:
            lineas.append({"account_id": ids[codigo], "debit": str(-neto), "credit": "0"})
    return await _publicar(
        db, empresa_id=empresa_id, fy=fy,
        concepto=f"Cierre {fy.year}", lineas=lineas, actor=actor,
    )


async def cerrar_ejercicio(
    db: AsyncSession,
    *,
    empresa_id: int,
    year: int,
    actor: str | None = None,
    ip: str | None = None,
) -> dict:
    """Regulariza (6/7→129), salda el balance, bloquea el ejercicio y audita."""
    fy = await _fiscal_year_bloqueado(db, empresa_id, year)
    await _sin_borradores(db, empresa_id, fy)
    regularizacion = await _regularizar(db, empresa_id, fy, actor)
    cierre = await _cerrar_saldos(db, empresa_id, fy, actor)
    fy.is_closed = True
    fy.closed_at = datetime.now(timezone.utc)
    fy.regularizacion_entry_id = regularizacion.id if regularizacion is not None else None
    fy.cierre_entry_id = cierre.id if cierre is not None else None
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CLOSE_YEAR",
        entity="fiscal_year",
        entity_id=fy.id,
        ip=ip,
        payload={
            "year": str(year),
            "regularizacion_entry_id": (
                str(regularizacion.id) if regularizacion is not None else None
            ),
            "cierre_entry_id": str(cierre.id) if cierre is not None else None,
        },
    )
    await db.flush()
    return {
        "year": year,
        "is_closed": True,
        "regularizacion_entry_id": (
            str(regularizacion.id) if regularizacion is not None else None
        ),
        "cierre_entry_id": str(cierre.id) if cierre is not None else None,
    }
