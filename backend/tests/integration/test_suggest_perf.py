"""Tests SPEC-001 Polish (T040): suggest < 1 s p95 y árbol < 500 ms con ~10k cuentas."""

from __future__ import annotations

import time
from statistics import quantiles

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.account_service import suggest
from services.acct.plan_tree import build_tree


async def _sembrar_10k(db: AsyncSession, tenant_id: int = 10) -> None:
    db.add(
        Company(company_id=tenant_id, nif=f"T{tenant_id:08d}", razon_social="E SL")
    )
    await db.flush()
    nivel: dict[str, int] = {}
    for codigo in (
        ["4"]
        + [f"4{d}" for d in range(10)]
        + [f"4{d}{e}" for d in range(10) for e in range(10)]
        + [f"4{d}{e}{f}" for d in range(10) for e in range(10) for f in range(10)]
    ):
        cuenta = AccountPlan(
            tenant_id=tenant_id, code=codigo, name=f"C-{codigo}",
            parent_id=nivel.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True,
        )
        db.add(cuenta)
        await db.flush()
        nivel[codigo] = cuenta.id
    hijas = [
        AccountPlan(
            tenant_id=tenant_id, code=f"{padre}{g}", name=f"C-{padre}{g}",
            parent_id=pid, level=5, is_active=True,
        )
        for padre, pid in list(nivel.items())
        if len(padre) == 4 and padre < "4900"
        for g in range(10)
    ]
    db.add_all(hijas)
    await db.flush()


def _p95(muestras: list[float]) -> float:
    return quantiles(muestras, n=100)[94]


@pytest.mark.benchmark
async def test_suggest_menos_1s_p95(db_session: AsyncSession) -> None:
    await _sembrar_10k(db_session)
    tiempos = []
    for _ in range(20):
        inicio = time.perf_counter()
        items = await suggest(db_session, 10, "400", limit=20)
        tiempos.append(time.perf_counter() - inicio)
    assert len(items) > 0
    assert _p95(tiempos) < 1.0


@pytest.mark.benchmark
async def test_arbol_menos_500ms(db_session: AsyncSession) -> None:
    await _sembrar_10k(db_session)
    tiempos = []
    for _ in range(10):
        inicio = time.perf_counter()
        nodos = await build_tree(db_session, 10)
        tiempos.append(time.perf_counter() - inicio)
    assert len(nodos) == 1
    assert _p95(tiempos) < 0.5
