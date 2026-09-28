"""Tests SPEC-001 T038: hardening multi-tenant, flujo completo cross-empresa."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.account_service import (
    AccountError,
    actualizar_cuenta,
    crear_cuenta,
    suggest,
)
from services.acct.plan_tree import build_tree, obtener_cuenta
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


async def _flujo_completo_atacante_victima(db: AsyncSession, atacante: int, victima: int) -> None:
    cuenta_victima = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == victima, AccountPlan.code == "4300"
        )
    )
    assert cuenta_victima is not None

    # 1. Consulta: árbol del atacante sin nodos de la víctima
    arbol = await build_tree(db, atacante)
    assert cuenta_victima.id not in {n["id"] for n in _aplanar(arbol)}

    # 2. Detalle por ID de la víctima → None (equivale a 404)
    assert await obtener_cuenta(db, atacante, cuenta_victima.id) is None

    # 3. Suggest del atacante sin datos de la víctima
    items = await suggest(db, atacante, q="430")
    assert items and all(i["tenant_id"] == atacante for i in items)

    # 4. Alta con padre de la víctima → parent_not_found (equivale a 404)
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db, atacante, "43000001", "Hack", cuenta_victima.id)
    assert exc.value.code == "parent_not_found"

    # 5. Edición sobre ID de la víctima → not_found (equivale a 404)
    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db, atacante, cuenta_victima.id, name="hack")
    assert exc.value.code == "not_found"


async def test_cross_tenant_full_a_sobre_b(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)
    await _flujo_completo_atacante_victima(db_session, atacante=1, victima=2)


async def test_cross_tenant_full_b_sobre_a(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)
    await _flujo_completo_atacante_victima(db_session, atacante=2, victima=1)
