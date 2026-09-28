"""Helpers compartidos de SPEC-025 (catalogo versionado)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from services.catalog._comun import crear_version_completa
from services.journal.entry_service import asentar, crear_borrador
from tests.conftest import sembrar_empresa_pgc

__all__ = [
    "cuenta_id",
    "objetivo_2026",
    "plan_ids",
    "plantar_431",
    "postear",
    "preparar_trasvase",
    "sembrar_base",
]


async def plantar_431(db: AsyncSession, tenant_id: int = 10) -> None:
    """Siembra la cuenta grupo 431 (padre de 4310) si falta en el plan."""
    padre = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == tenant_id,
            AccountPlan.code == "43",
            AccountPlan.level == 2,
        )
    )
    if padre is None:
        return
    existente = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == tenant_id, AccountPlan.code == "431"
        )
    )
    if existente is None:
        db.add(
            AccountPlan(
                tenant_id=tenant_id,
                code="431",
                level=3,
                name="Clientes (otros)",
                parent_id=padre.id,
                is_selectable=False,
            )
        )
        await db.flush()


async def sembrar_base(
    db: AsyncSession,
    empresa_id: int = 10,
    *,
    codigo: str = "BASE-2025",
    vigente: bool = True,
) -> str:
    """Empresa + PGC + 431 + version base 2025 (vigente por defecto)."""
    await sembrar_empresa_pgc(db, empresa_id)
    await plantar_431(db, empresa_id)
    version = await crear_version_completa(
        db,
        empresa_id=empresa_id,
        codigo=codigo,
        fecha_inicio=date(2025, 1, 1),
        fecha_fin=date(2025, 12, 31),
        operaciones=[],
        mapeo_explicito=[],
        actor="test",
    )
    if vigente:
        version.estado = EstadoVersion.vigente
        await db.flush()
    return str(version.id)


async def cuenta_id(db: AsyncSession, code: str, empresa_id: int = 10) -> int:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
        )
    )
    assert cuenta is not None, f"cuenta {code} no existe en la empresa {empresa_id}"
    return int(cuenta.id)


async def plan_ids(db: AsyncSession, empresa_id: int = 10) -> dict[str, int]:
    filas = await db.execute(
        select(AccountPlan.code, AccountPlan.id).where(
            AccountPlan.tenant_id == empresa_id
        )
    )
    return {code: int(ident) for code, ident in filas.all()}


async def postear(
    db: AsyncSession,
    empresa_id: int,
    fecha: date,
    lineas: list[dict[str, Any]],
    concepto: str = "Movimiento de test",
) -> uuid.UUID:
    """Publica un asiento POSTED (para sembrar saldos del ejercicio)."""
    borrador = await crear_borrador(
        db,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto=concepto,
        lineas=lineas,
        actor="test",
    )
    asiento = await asentar(
        db, empresa_id=empresa_id, entry_id=borrador.id, actor="test"
    )
    return asiento.id


async def objetivo_2026(
    db: AsyncSession,
    empresa_id: int = 10,
    *,
    codigo: str = "NORMA-2026",
    operaciones: list[dict[str, Any]] | None = None,
) -> CatalogoVersion:
    """Version destino 2026: alta 4310 + renombrado 4300 -> 4310 por defecto."""
    if operaciones is None:
        operaciones = [
            {
                "operacion": "alta",
                "codigo": "4310",
                "nombre": "Clientes pagos",
                "padre_codigo": "431",
            },
            {
                "operacion": "renombrado",
                "codigo": "4300",
                "nombre": "Clientes euros",
                "destino_codigo": "4310",
            },
        ]
    return await crear_version_completa(
        db,
        empresa_id=empresa_id,
        codigo=codigo,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        operaciones=operaciones,
        mapeo_explicito=[],
        actor="test",
    )


async def preparar_trasvase(
    db: AsyncSession, empresa_id: int = 10, *, importe: str = "12500.0000"
) -> tuple[str, str, dict[str, int]]:
    """BASE-2025 vigente + objetivo 2026 + saldo 4300 en el ejercicio 2025.

    Devuelve ``(version_base_id, version_objetivo_id, ids_del_plan)``.
    """
    base_id = await sembrar_base(db, empresa_id)
    objetivo = await objetivo_2026(db, empresa_id)
    ids = await plan_ids(db, empresa_id)
    await postear(
        db,
        empresa_id,
        date(2025, 6, 30),
        [
            {"account_id": ids["4300"], "debit": importe, "credit": "0"},
            {"account_id": ids["1110"], "debit": "0", "credit": importe},
        ],
        concepto="Cobro de cliente 2025",
    )
    return base_id, str(objetivo.id), ids
