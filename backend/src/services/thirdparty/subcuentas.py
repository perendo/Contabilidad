"""Automatic subaccount assignment for terceros (SPEC-008 T020)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.ar.tercero_subcuenta import TerceroSubcuenta, TipoSubcuenta

RAIZ_CLIENTE = "430"
RAIZ_PROVEEDOR = "410"


class SubcuentaError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _siguiente_codigo(db: AsyncSession, empresa_id: int, raiz: str) -> str:
    """Smallest free 4-digit code under the root (5-digit fallback).

    The seed already occupies e.g. ``4300``, so the first tercero gets
    ``4301``. ``level == len(code)`` is enforced by the SPEC-001 trigger.
    """
    existentes = set(
        (
            await db.scalars(
                select(AccountPlan.code).where(
                    AccountPlan.tenant_id == empresa_id,
                    AccountPlan.code.like(f"{raiz}%"),
                )
            )
        ).all()
    )
    for n in range(10):
        codigo = f"{raiz}{n}"
        if len(codigo) == 4 and codigo not in existentes:
            return codigo
    for n in range(100):
        codigo = f"{raiz}{n:02d}"
        if len(codigo) == 5 and codigo not in existentes:
            return codigo
    raise SubcuentaError(
        "sin_codigos_libres", f"No hay códigos de subcuenta libres bajo {raiz}"
    )


async def _padre(db: AsyncSession, empresa_id: int, raiz: str) -> AccountPlan:
    padre = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == raiz,
            AccountPlan.is_active.is_(True),
        )
    )
    if padre is None:
        raise SubcuentaError(
            "cuenta_raiz_no_existe",
            f"La cuenta {raiz} no existe en el plan de la empresa activa",
        )
    return padre


async def asignar_subcuentas(
    db: AsyncSession,
    empresa_id: int,
    tercero_id: uuid.UUID,
    *,
    es_cliente: bool,
    es_proveedor: bool,
) -> list[TerceroSubcuenta]:
    """Create one level-4 subaccount per active role under 430/410."""
    asignadas: list[TerceroSubcuenta] = []
    for activo, raiz, tipo in (
        (es_cliente, RAIZ_CLIENTE, TipoSubcuenta.CLIENTE),
        (es_proveedor, RAIZ_PROVEEDOR, TipoSubcuenta.PROVEEDOR),
    ):
        if not activo:
            continue
        padre = await _padre(db, empresa_id, raiz)
        codigo = await _siguiente_codigo(db, empresa_id, raiz)
        db.add(
            AccountPlan(
                tenant_id=empresa_id,
                code=codigo,
                name=f"Tercero {codigo}",
                parent_id=padre.id,
                level=4,
                is_active=True,
                is_selectable=True,
            )
        )
        await db.flush()
        subcuenta = TerceroSubcuenta(
            empresa_id=empresa_id,
            tercero_id=tercero_id,
            tipo=tipo,
            cuenta_codigo=codigo,
        )
        db.add(subcuenta)
        await db.flush()
        asignadas.append(subcuenta)
    return asignadas
