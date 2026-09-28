"""Tests SPEC-002 Foundational (T011): asiento de A invisible desde B (modelo)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry
from models.iam.company import Company
from services.journal.entry_service import asentar, crear_borrador


async def _pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    db.add(
        Company(company_id=tenant_id, nif=f"T{tenant_id:08d}", razon_social="E SL")
    )
    await db.flush()
    ids: dict[str, int] = {}
    for codigo in ("4", "43", "430", "4300", "5", "57", "572", "5720"):
        cuenta = AccountPlan(
            tenant_id=tenant_id, code=codigo, name=f"C-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=len(codigo) >= 4,
        )
        db.add(cuenta)
        await db.flush()
        ids[codigo] = cuenta.id
    return ids


async def test_asiento_a_invisible_en_todas_las_consultas_de_b(
    db_session: AsyncSession,
) -> None:
    cuentas = await _pgc(db_session, 10)
    await _pgc(db_session, 20)
    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 5, 1), concepto="V",
        lineas=[
            {"account_id": cuentas["4300"], "debit": "10.0000", "credit": "0"},
            {"account_id": cuentas["5720"], "debit": "0", "credit": "10.0000"},
        ],
        actor="test",
    )
    sentado = await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="test")
    assert await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == 20, JournalEntry.id == sentado.id
        )
    ) is None
    assert await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == 20, JournalEntry.ejercicio == 2026
        )
    ) is None
    assert await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == 10, JournalEntry.id == sentado.id
        )
    ) is not None
