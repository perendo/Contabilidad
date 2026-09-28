"""Tests SPEC-004 US1 (T013): agregación por nivel con roll-up por prefijo."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from services.journal.entry_service import asentar, crear_borrador
from services.reports.common import rollup_code
from services.reports.trial_balance import trial_balance
from tests.conftest import crear_empresa


def test_rollup_por_prefijo() -> None:
    assert rollup_code("4300", 2) == "43"
    assert rollup_code("5720", 1) == "5"
    assert rollup_code("43", 4) == "43"
    with pytest.raises(ValueError):
        rollup_code("4300", 0)


async def test_nivel_superior_al_plan_agrega_sin_error(db_session: AsyncSession) -> None:
    await crear_empresa(db_session, 10, nif="T00000010", razon_social="Empresa 10 SL")
    await db_session.flush()
    ids: dict[str, int] = {}
    for codigo in ("4", "43", "430", "4300", "5", "57", "572", "5720"):
        cuenta = AccountPlan(
            tenant_id=10, code=codigo, name=f"C-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=len(codigo) >= 4,
        )
        db_session.add(cuenta)
        await db_session.flush()
        ids[codigo] = cuenta.id
    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 3, 1), concepto="V",
        lineas=[
            {"account_id": ids["4300"], "debit": "10.0000", "credit": "0"},
            {"account_id": ids["5720"], "debit": "0", "credit": "10.0000"},
        ],
        actor="test",
    )
    await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="test")
    balance = await trial_balance(
        db_session, empresa_id=10,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), level=8,
    )
    assert balance["cuadra"] is True
    assert {i["code"] for i in balance["items"]} == {"4300", "5720"}
    nivel1 = await trial_balance(
        db_session, empresa_id=10,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), level=1,
    )
    assert {i["code"] for i in nivel1["items"]} == {"4", "5"}
