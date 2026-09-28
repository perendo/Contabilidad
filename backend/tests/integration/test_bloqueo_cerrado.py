"""Tests SPEC-004 US3 (T031): ejercicio cerrado bloquea crear/asentar/reversar."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry
from services.closing.close_year import cerrar_ejercicio
from services.journal.entry_service import AsientoError, asentar, crear_borrador
from services.journal.reversal import anular
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


async def test_bloqueo_crear_asentar_reversar_en_cerrado(db_session: AsyncSession) -> None:
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
            {"account_id": ids["6000"], "debit": "50.0000", "credit": "0"},
            {"account_id": ids["5720"], "debit": "0", "credit": "50.0000"},
        ],
        actor="test",
    )
    sentado = await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="test")
    await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")

    with pytest.raises(AsientoError) as exc:
        await crear_borrador(
            db_session, empresa_id=10, fecha=date(2026, 5, 1), concepto="X",
            lineas=[
                {"account_id": ids["6000"], "debit": "1.0000", "credit": "0"},
                {"account_id": ids["5720"], "debit": "0", "credit": "1.0000"},
            ],
            actor="test",
        )
    assert exc.value.code == "ejercicio_cerrado"

    with pytest.raises(AsientoError) as exc2:
        await anular(
            db_session, empresa_id=10, entry_id=sentado.id,
            actor="test", fecha=date(2026, 5, 1),
        )
    assert exc2.value.code == "ejercicio_cerrado"

    n = await db_session.scalar(
        select(func.count(JournalEntry.id)).where(JournalEntry.empresa_id == 10)
    )
    assert n == 3
