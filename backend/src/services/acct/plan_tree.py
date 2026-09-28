"""Account-forest service (SPEC-001 US1): build_tree + get_by_id, tenant-scoped."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan


def _nodo(cuenta: AccountPlan) -> dict:
    return {
        "id": cuenta.id,
        "code": cuenta.code,
        "name": cuenta.name,
        "level": cuenta.level,
        "is_selectable": cuenta.is_selectable,
        "is_active": cuenta.is_active,
        "parent_id": cuenta.parent_id,
        "children": [],
    }


async def build_tree(db: AsyncSession, tenant_id: int) -> list[dict]:
    """Return the full account tree for one tenant (one query, no N+1)."""
    cuentas = (
        await db.scalars(
            select(AccountPlan)
            .where(AccountPlan.tenant_id == tenant_id)
            .order_by(AccountPlan.code)
        )
    ).all()
    nodos = {c.id: _nodo(c) for c in cuentas}
    raices: list[dict] = []
    for cuenta in cuentas:
        nodo = nodos[cuenta.id]
        if cuenta.parent_id is not None and cuenta.parent_id in nodos:
            nodos[cuenta.parent_id]["children"].append(nodo)
        else:
            raices.append(nodo)
    return raices


async def obtener_cuenta(db: AsyncSession, tenant_id: int, account_id: int) -> AccountPlan | None:
    """Fetch an account scoped to the tenant (never leaks other tenants)."""
    return await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == tenant_id, AccountPlan.id == account_id
        )
    )