"""Tests SPEC-001 US2 (T017-T018): suggest solo apuntables y aislamiento."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from services.acct.account_service import SuggestError, suggest
from services.acct.seed import seed_default_pgc


async def _sembrar(db: AsyncSession, tenant_id: int) -> None:
    db.add(
        Company(
            company_id=tenant_id,
            nif=f"NIF-{tenant_id}",
            razon_social=f"Empresa {tenant_id}",
        )
    )
    await db.flush()
    await seed_default_pgc(db, tenant_id)


async def test_suggest_solo_apuntables(db_session: AsyncSession) -> None:
    await _sembrar(db_session, 1)
    items = await suggest(db_session, tenant_id=1, q="430")
    assert items, "debe devolver la subcuenta 4300"
    assert all(i["is_selectable"] and i["is_active"] for i in items)
    assert all(len(i["code"]) >= 4 for i in items)


async def test_suggest_por_nombre(db_session: AsyncSession) -> None:
    await _sembrar(db_session, 1)
    items = await suggest(db_session, tenant_id=1, q="Bancos")
    assert any(i["code"] == "5720" for i in items)


async def test_suggest_sin_coincidencias_lista_vacia(db_session: AsyncSession) -> None:
    await _sembrar(db_session, 1)
    items = await suggest(db_session, tenant_id=1, q="zzzz")
    assert items == []


async def test_suggest_q_vacio_rechazado(db_session: AsyncSession) -> None:
    with pytest.raises(SuggestError):
        await suggest(db_session, tenant_id=1, q="")


async def test_suggest_aislamiento(db_session: AsyncSession) -> None:
    await _sembrar(db_session, 1)
    await _sembrar(db_session, 2)
    items_a = await suggest(db_session, tenant_id=1, q="430")
    assert all(i["tenant_id"] == 1 for i in items_a)
