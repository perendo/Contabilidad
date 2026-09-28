"""Tests SPEC-004 US3 (T028): segundo cierre → 409 sin duplicados."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryTipo
from services.closing.close_year import CierreError, cerrar_ejercicio
from services.journal.entry_service import asentar, crear_borrador
from tests.conftest import crear_empresa


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


async def test_doble_cierre_409_sin_duplicados(db_session: AsyncSession) -> None:
    await crear_empresa(db_session, 10, nif="T00000010", razon_social="Empresa 10 SL")
    await db_session.flush()
    ids: dict[str, int] = {}
    for codigo in ("1", "12", "129", "5", "57", "572", "5720", "6", "60", "600", "6000"):
        ids[codigo] = await _cuenta(
            db_session, 10, codigo,
            ids.get(codigo[:-1]) if len(codigo) > 1 else None,
        )
    db_session.add(
        FiscalYear(
            empresa_id=10, year=2026,
            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31),
        )
    )
    await db_session.flush()
    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 5, 1), concepto="G",
        lineas=[
            {"account_id": ids["6000"], "debit": "10.0000", "credit": "0"},
            {"account_id": ids["5720"], "debit": "0", "credit": "10.0000"},
        ],
        actor="test",
    )
    await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="test")
    await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    with pytest.raises(CierreError) as exc:
        await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    assert exc.value.code == "ejercicio_cerrado"
    n = len(
        (
            await db_session.scalars(
                select(JournalEntry).where(
                    JournalEntry.empresa_id == 10,
                    JournalEntry.tipo == JournalEntryTipo.ADJUSTMENT,
                )
            )
        ).all()
    )
    assert n == 2
