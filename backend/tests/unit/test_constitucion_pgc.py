"""Tests SPEC-001 T037: constitución V en los flujos del plan (apuntabilidad + aislamiento)."""

from __future__ import annotations

import inspect

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.acct.accounts import CuentaCreate, CuentaUpdate
from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct import account_service
from services.acct.plan_tree import build_tree
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


def _aplanar(nodos: list[dict]) -> list[dict]:
    planos: list[dict] = []
    for n in nodos:
        planos.append(n)
        planos.extend(_aplanar(n["children"]))
    return planos


async def test_apuntabilidad_solo_hojas_nivel_ge_4_en_tree(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    arbol = await build_tree(db_session, 1)
    for nodo in _aplanar(arbol):
        if nodo["is_selectable"]:
            assert nodo["level"] >= 4
            assert nodo["children"] == []
        if nodo["children"]:
            assert nodo["is_selectable"] is False


async def test_suggest_solo_apuntables_activas(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    items = await account_service.suggest(db_session, 1, q="4")
    assert items
    assert all(i["is_selectable"] and i["is_active"] and i["level"] >= 4 for i in items)


async def test_alta_respeta_apuntabilidad_derivada(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    padre_n4 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    hoja = await account_service.crear_cuenta(db_session, 1, "43000001", "Hoja", padre_n4.id)
    assert hoja.is_selectable is True
    grupo = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "1")
    )
    rama = await account_service.crear_cuenta(db_session, 1, "18", "Rama", grupo.id)
    assert rama.is_selectable is False


async def test_edicion_no_expone_is_selectable(db_session: AsyncSession) -> None:
    params = inspect.signature(account_service.actualizar_cuenta).parameters
    assert "is_selectable" not in params
    assert set(params) >= {"db", "tenant_id", "account_id", "name", "is_active"}


async def test_servicios_exigen_tenant_id_explicito() -> None:
    for fn in (
        account_service.suggest,
        account_service.crear_cuenta,
        account_service.actualizar_cuenta,
    ):
        assert "tenant_id" in inspect.signature(fn).parameters


async def test_schemas_sin_tenant_en_body() -> None:
    assert "tenant_id" not in CuentaCreate.model_fields
    assert "empresa_id" not in CuentaCreate.model_fields
    assert "tenant_id" not in CuentaUpdate.model_fields
    assert "empresa_id" not in CuentaUpdate.model_fields


async def test_aislamiento_tenant_en_flujos(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    arbol_1 = await build_tree(db_session, 1)
    ids_1 = {n["id"] for n in _aplanar(arbol_1)}
    for i in ids_1:
        assert await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.id == i)
        ) is None

    items_1 = await account_service.suggest(db_session, 1, q="430")
    assert items_1 and all(i["tenant_id"] == 1 for i in items_1)

    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    hija = await account_service.crear_cuenta(db_session, 1, "43000001", "Cliente", padre_1.id)
    assert hija.tenant_id == 1
    editada = await account_service.actualizar_cuenta(db_session, 1, hija.id, name="Cliente X")
    assert editada.name == "Cliente X"
