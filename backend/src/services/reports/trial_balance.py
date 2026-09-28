"""Balance de sumas y saldos (SPEC-004 US1): agregado derivado, sin tabla propia.

Solo computan los asientos ``POSTED`` (libro oficial); los borradores no
forman parte del balance. Toda la aritmética es ``Decimal``.
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
from services.reports.common import cuantizar, fmt, rollup_code


class BalanceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def trial_balance(
    db: AsyncSession,
    *,
    empresa_id: int,
    date_from: date,
    date_to: date,
    level: int = 4,
) -> dict:
    """Aggregate Debe/Haber/saldo por cuenta al nivel pedido + consolidados."""
    if date_from > date_to:
        raise BalanceError("rango_invertido", "date_from no puede ser posterior a date_to")
    if level < 1:
        raise BalanceError("nivel_invalido", "level debe ser >= 1")

    filas = (
        await db.execute(
            select(
                JournalEntryLine.cuenta,
                JournalEntryLine.debe,
                JournalEntryLine.haber,
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
                JournalEntry.fecha >= date_from,
                JournalEntry.fecha <= date_to,
            )
            .order_by(JournalEntryLine.cuenta)
        )
    ).all()

    grupos: dict[str, dict[str, Decimal]] = {}
    for cuenta, debe, haber in filas:
        clave = rollup_code(cuenta, level)
        g = grupos.setdefault(clave, {"debe": Decimal(0), "haber": Decimal(0)})
        g["debe"] += debe
        g["haber"] += haber

    nombres = {
        code: name
        for code, name in (
            await db.execute(
                select(AccountPlan.code, AccountPlan.name).where(
                    AccountPlan.tenant_id == empresa_id
                )
            )
        ).all()
    }

    items = [
        {
            "code": code,
            "name": nombres.get(code, ""),
            "debe": fmt(g["debe"]),
            "haber": fmt(g["haber"]),
            "saldo": fmt(g["debe"] - g["haber"]),
        }
        for code, g in sorted(grupos.items())
    ]
    total_debe = sum((g["debe"] for g in grupos.values()), Decimal(0))
    total_haber = sum((g["haber"] for g in grupos.values()), Decimal(0))
    return {
        "total_debe": fmt(total_debe),
        "total_haber": fmt(total_haber),
        "cuadra": cuantizar(total_debe) == cuantizar(total_haber),
        "items": items,
    }
