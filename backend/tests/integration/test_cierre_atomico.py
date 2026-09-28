"""Tests SPEC-004 US3 (T027/T031): atomicidad y bloqueo de ejercicio cerrado."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryTipo
from models.iam.company import Company
from services.closing import close_year
from services.closing.close_year import cerrar_ejercicio
from services.journal.entry_service import asentar, crear_borrador


async def _pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    db.add(
        Company(company_id=tenant_id, nif=f"T{tenant_id:08d}", razon_social="E SL")
    )
    await db.flush()
    ids: dict[str, int] = {}
    for codigo in ("1", "12", "129", "5", "57", "572", "5720", "6", "60", "600", "6000"):
        ids[codigo] = await _cuenta(db, tenant_id, codigo, ids.get(codigo[:-1]) if len(codigo) > 1 else None)
    db.add(
        FiscalYear(
            empresa_id=tenant_id, year=2026,
            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31),
        )
    )
    await db.flush()
    return ids


async def _cuenta(
    db: AsyncSession, tenant_id: int, codigo: str, padre: int | None
) -> int:
    cuenta = AccountPlan(
        tenant_id=tenant_id, code=codigo, name=f"C-{codigo}",
        parent_id=padre, level=len(codigo), is_active=True, is_selectable=True,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta.id


async def _gasto(db: AsyncSession, tenant_id: int, c: dict[str, int]):
    borrador = await crear_borrador(
        db, empresa_id=tenant_id, fecha=date(2026, 5, 1), concepto="G",
        lineas=[
            {"account_id": c["6000"], "debit": "50.0000", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "50.0000"},
        ],
        actor="test",
    )
    return await asentar(db, empresa_id=tenant_id, entry_id=borrador.id, actor="test")


async def test_fallo_mitad_no_deja_rastro(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = await _pgc(db_session, 10)
    await _gasto(db_session, 10, c)
    await db_session.commit()

    real_asentar = close_year.asentar

    async def _roto(*args, **kwargs):
        raise RuntimeError("fallo inyectado")

    monkeypatch.setattr(close_year, "asentar", _roto)
    with pytest.raises(RuntimeError, match="fallo inyectado"):
        await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    await db_session.rollback()
    assert real_asentar is not None
    n = await db_session.scalar(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.empresa_id == 10,
            JournalEntry.tipo == JournalEntryTipo.ADJUSTMENT,
        )
    )
    assert n == 0
    fy = await db_session.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == 10, FiscalYear.year == 2026)
    )
    assert fy is not None and not fy.is_closed
