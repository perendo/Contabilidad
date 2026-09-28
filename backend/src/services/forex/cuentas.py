"""Cuentas de diferencias de cambio (6680/7690) garantizadas en el plan.

El PGC base (SPEC-001) no incluye las ramas 668/769; cuando hace falta
(línea de redondeo en un asiento en divisa o el asiento de valoración a
cierre) se garantiza la cadena completa respetando ``level == len(code)`` y
los triggers de estructura de ``account_plan``:
  - 6 -> 66 -> 668 -> 6680  (gastos/diferencias negativas)
  - 7 -> 76 -> 769 -> 7690  (ingresos/diferencias positivas)
Solo la subcuenta de nivel 4 queda apuntable (``is_selectable``).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from services.forex.errores import ForexError

Lado = Literal["debe", "haber"]

_RAMAS: dict[Lado, tuple[tuple[str, str], tuple[str, str], tuple[str, str]]] = {
    "debe": (
        ("66", "Gastos financieros"),
        ("668", "Diferencias negativas de cambio"),
        ("6680", "Diferencias negativas de cambio"),
    ),
    "haber": (
        ("76", "Ingresos financieros"),
        ("769", "Diferencias positivas de cambio"),
        ("7690", "Diferencias positivas de cambio"),
    ),
}


async def _buscar(db: AsyncSession, tenant_id: int, codigo: str) -> AccountPlan | None:
    return await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == tenant_id,
            AccountPlan.code == codigo,
        )
    )


async def _crear(
    db: AsyncSession,
    tenant_id: int,
    codigo: str,
    nombre: str,
    nivel: int,
    padre: AccountPlan | None,
    *,
    apuntable: bool = False,
) -> AccountPlan:
    cuenta = AccountPlan(
        tenant_id=tenant_id,
        code=codigo,
        name=nombre,
        level=nivel,
        parent_id=padre.id if padre is not None else None,
        is_selectable=apuntable,
        is_active=True,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta


async def cuenta_diferencia_cambio(
    db: AsyncSession,
    empresa_id: int,
    lado: Lado,
) -> AccountPlan:
    """Garantiza la subcuenta apuntable 6680 (debe) o 7690 (haber)."""
    (sub_codigo, sub_nombre), (n3_codigo, n3_nombre), (n4_codigo, n4_nombre) = _RAMAS[lado]
    grupo_codigo = "6" if lado == "debe" else "7"
    grupo = await _buscar(db, empresa_id, grupo_codigo)
    if grupo is None:
        raise ForexError(
            "plan_incompleto",
            f"Grupo {grupo_codigo} del PGC no encontrado en la empresa activa",
        )
    sub = await _buscar(db, empresa_id, sub_codigo)
    if sub is None:
        sub = await _crear(db, empresa_id, sub_codigo, sub_nombre, 2, grupo)
    n3 = await _buscar(db, empresa_id, n3_codigo)
    if n3 is None:
        n3 = await _crear(db, empresa_id, n3_codigo, n3_nombre, 3, sub)
    n4 = await _buscar(db, empresa_id, n4_codigo)
    if n4 is None:
        n4 = await _crear(db, empresa_id, n4_codigo, n4_nombre, 4, n3, apuntable=True)
    elif not n4.is_selectable:
        n4.is_selectable = True
        await db.flush()
    return n4