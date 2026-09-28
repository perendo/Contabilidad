"""Saldos por cuenta para informes (SPEC-010 T007).

Agrega ``JournalEntryLine`` por ``(empresa_id, ejercicio, cuenta)`` considerando
solo asientos ``POSTED`` (libro oficial). Los importes se computan en
``Decimal`` exacto; nunca ``float`` (constitucion). Permite excluir el asiento de
cierre (y/o el de regularizacion) para reconstruir los saldos de gestion.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
)


class ReportingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def error(code: str, message: str) -> ReportingError:
    return ReportingError(code, message)


async def fiscal_year(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> FiscalYear | None:
    return await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id,
            FiscalYear.year == ejercicio,
        )
    )


async def _excluidos(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> set[uuid.UUID]:
    fy = await fiscal_year(db, empresa_id, ejercicio)
    if fy is None:
        return set()
    return {
        ident
        for ident in (fy.regularizacion_entry_id, fy.cierre_entry_id)
        if ident is not None
    }


async def netos_por_cuenta(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    excluir_cierre: bool = False,
    excluir_regularizacion: bool = False,
) -> dict[str, Decimal]:
    """Neto (debe - haber) por codigo de cuenta del ejercicio (POSTED)."""
    excluir: set[uuid.UUID] = set()
    if excluir_cierre or excluir_regularizacion:
        fy = await fiscal_year(db, empresa_id, ejercicio)
        if fy is not None:
            if excluir_cierre and fy.cierre_entry_id is not None:
                excluir.add(fy.cierre_entry_id)
            if excluir_regularizacion and fy.regularizacion_entry_id is not None:
                excluir.add(fy.regularizacion_entry_id)

    query = (
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
            JournalEntry.ejercicio == ejercicio,
        )
    )
    if excluir:
        query = query.where(JournalEntry.id.notin_(excluir))

    netos: dict[str, Decimal] = {}
    for cuenta, debe, haber in (await db.execute(query)).all():
        netos[cuenta] = netos.get(cuenta, Decimal(0)) + debe - haber
    return {codigo: neto for codigo, neto in netos.items() if neto != 0}


def es_gasto(codigo: str) -> bool:
    return codigo[:1] == "6"


def es_ingreso(codigo: str) -> bool:
    return codigo[:1] == "7"


def resultado_de_gestion(netos: dict[str, Decimal]) -> Decimal:
    """Ingresos - Gastos a partir de los netos de los grupos 6 y 7."""
    gastos = sum((n for c, n in netos.items() if es_gasto(c)), Decimal(0))
    ingresos = -sum((n for c, n in netos.items() if es_ingreso(c)), Decimal(0))
    return ingresos - gastos