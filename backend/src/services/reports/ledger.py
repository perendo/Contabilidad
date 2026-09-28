"""Libro mayor de subcuenta (SPEC-004 US2): extracto cronológico con saldo acumulado.

Solo computan los asientos ``POSTED``. Toda la aritmética es ``Decimal``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
)
from services.reports.common import fmt


class LedgerError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def ledger(
    db: AsyncSession,
    *,
    empresa_id: int,
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Movements of one account with running balance (both in 4-decimal strings)."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise LedgerError("rango_invertido", "date_from no puede ser posterior a date_to")
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.id == account_id
        )
    )
    if cuenta is None:
        raise LedgerError(
            "cuenta_no_encontrada", "Subcuenta inexistente en la empresa activa"
        )

    condiciones = [
        JournalEntryLine.empresa_id == empresa_id,
        JournalEntryLine.account_id == account_id,
        JournalEntry.empresa_id == empresa_id,
        JournalEntry.estado == JournalEntryEstado.POSTED,
    ]
    if date_from is not None:
        condiciones.append(JournalEntry.fecha >= date_from)
    if date_to is not None:
        condiciones.append(JournalEntry.fecha <= date_to)

    filas = (
        await db.execute(
            select(
                JournalEntry.fecha,
                JournalEntry.numero_asiento,
                JournalEntry.concepto,
                JournalEntryLine.debe,
                JournalEntryLine.haber,
            )
            .join(
                JournalEntry,
                (JournalEntryLine.journal_entry_id == JournalEntry.id)
                & (JournalEntryLine.empresa_id == JournalEntry.empresa_id),
            )
            .where(*condiciones)
            .order_by(JournalEntry.fecha, JournalEntry.numero_asiento)
        )
    ).all()

    movimientos = []
    saldo = Decimal(0)
    for fecha, numero, concepto, debe, haber in filas:
        saldo += debe - haber
        movimientos.append(
            {
                "fecha": fecha.isoformat(),
                "numero": numero,
                "concepto": concepto,
                "debe": fmt(debe),
                "haber": fmt(haber),
                "saldo_acumulado": fmt(saldo),
            }
        )
    return {
        "cuenta": {"id": cuenta.id, "code": cuenta.code, "name": cuenta.name},
        "saldo_inicial": "0.0000",
        "movimientos": movimientos,
        "saldo_final": fmt(saldo),
    }
