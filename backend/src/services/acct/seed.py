"""Seed PGC (SPEC-001 T008): idempotent base catalogue per tenant.

Python counterpart of `002_seed_pgc.sql` for SQLite/CI environments; the PG
deployment uses the stored procedure via `trg_companies_seed`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from services.audit.writer import audit_escribir

GRUPOS = [
    ("1", "Financiación básica"),
    ("2", "Inmovilizado"),
    ("3", "Existencias"),
    ("4", "Acreedores y deudores por operaciones comerciales"),
    ("5", "Cuentas financieras"),
    ("6", "Compras y gastos"),
    ("7", "Ventas e ingresos"),
]

SUBGRUPOS = [
    ("10", "Capital"),
    ("11", "Reservas y resultados"),
    ("12", "Resultados"),
    ("13", "Subvenciones y donaciones"),
    ("16", "Deudas a largo plazo"),
    ("17", "Deudas a largo plazo con entidades de crédito"),
    ("20", "Inmovilizaciones intangibles"),
    ("21", "Inmovilizaciones materiales"),
    ("25", "Inversiones financieras a largo plazo"),
    ("28", "Amortización acumulada"),
    ("30", "Existencias: mercaderías"),
    ("32", "Otros aprovisionamientos"),
    ("40", "Proveedores"),
    ("41", "Acreedores varios"),
    ("43", "Clientes"),
    ("46", "H.P. acreedora por conceptos fiscales"),
    ("47", "H.P. deudora por conceptos fiscales"),
    ("57", "Tesorería"),
    ("58", "Caja"),
    ("60", "Compras"),
    ("62", "Servicios exteriores"),
    ("63", "Impuestos sobre beneficios"),
    ("64", "Gastos de personal"),
    ("66", "Gastos financieros"),
    ("68", "Amortización del inmovilizado"),
    ("70", "Ventas de mercaderías"),
    ("75", "Otros ingresos de gestión"),
    ("77", "Subvenciones, donaciones y legados de explotación"),
    ("79", "Excesos y aplicaciones de provisiones y de pérdidas por deterioro"),
]

CUENTAS = [
    ("100", "Capital social"),
    ("111", "Patrimonio neto"),
    ("132", "Subvenciones oficiales de capital"),
    ("160", "Deudas a largo plazo"),
    ("210", "Terrenos y bienes naturales"),
    ("250", "Inversiones financieras a LP"),
    ("281", "Amortización acumulada del inmovilizado material"),
    ("300", "Mercaderías"),
    ("325", "Mercaderías en tránsito"),
    ("400", "Proveedores"),
    ("410", "Acreedores por prestaciones de servicios"),
    ("430", "Clientes"),
    ("470", "H.P. deudora por IVA"),
    ("473", "H.P. deudora por Impuesto sobre Sociedades"),
    ("475", "H.P. acreedora por conceptos fiscales"),
    ("570", "Caja"),
    ("572", "Bancos c/c"),
    ("600", "Compras de mercaderías"),
    ("621", "Arrendamientos y cánones"),
    ("630", "Impuesto sobre beneficios"),
    ("640", "Sueldos y salarios"),
    ("662", "Intereses de deudas"),
    ("681", "Amortización del inmovilizado material"),
    ("700", "Venta de mercaderías"),
    ("790", "Reversión del deterioro de existencias"),
]

SUBCUENTAS = [
    ("1110", "Patrimonio neto c/p", "111"),
    ("1320", "Subvenciones oficiales de capital c/p", "132"),
    ("2100", "Terrenos", "210"),
    ("2500", "Inversiones financieras a LP en capital", "250"),
    ("2810", "A.A. inmovilizado material", "281"),
    ("3000", "Mercaderías", "300"),
    ("4000", "Proveedores (euros)", "400"),
    ("4100", "Acreedores por prestaciones de servicios", "410"),
    ("4300", "Clientes (euros)", "430"),
    ("4700", "H.P. deudora por IVA soportado", "470"),
    ("4709", "H.P. acreedora por devoluciones", "470"),
    ("4730", "H.P. deudora por Impuesto sobre Sociedades", "473"),
    ("4751", "H.P. acreedora por retenciones e ingresos a cuenta", "475"),
    ("4752", "H.P. acreedora por retenciones e ingresos a cuenta", "475"),
    ("5720", "Bancos c/c vista euros", "572"),
    ("6000", "Compras de mercaderías", "600"),
    ("6210", "Arrendamientos", "621"),
    ("6300", "Impuesto sobre beneficios. Autoliquidacion", "630"),
    ("6400", "Sueldos y salarios", "640"),
    ("6810", "Amortización del inmovilizado material", "681"),
    ("7000", "Venta de mercaderías", "700"),
]


async def _ya_existe_plan(db: AsyncSession, tenant_id: int) -> bool:
    return (
        await db.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == tenant_id, AccountPlan.level == 1
            )
        )
    ) is not None


async def _asegurar_4751(db: AsyncSession, tenant_id: int) -> bool:
    existente = await db.scalar(
        select(AccountPlan.id).where(
            AccountPlan.tenant_id == tenant_id, AccountPlan.code == "4751"
        )
    )
    if existente is not None:
        return False
    padre = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == tenant_id,
            AccountPlan.code == "475",
            AccountPlan.level == 3,
        )
    )
    if padre is None:
        return False
    db.add(
        AccountPlan(
            tenant_id=tenant_id,
            code="4751",
            level=4,
            name="H.P. acreedora por retenciones e ingresos a cuenta",
            parent_id=padre.id,
            is_selectable=True,
        )
    )
    await db.flush()
    return True


async def _insertar(
    db: AsyncSession,
    tenant_id: int,
    code: str,
    level: int,
    name: str,
    *,
    parent: AccountPlan | None = None,
    is_selectable: bool = False,
) -> AccountPlan:
    cuenta = AccountPlan(
        tenant_id=tenant_id,
        code=code,
        level=level,
        name=name,
        parent_id=parent.id if parent else None,
        is_selectable=is_selectable,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta


async def seed_default_pgc(db: AsyncSession, tenant_id: int) -> int:
    """Idempotently seed the 7-group PGC base catalogue. Returns rows created."""
    if await _ya_existe_plan(db, tenant_id):
        if await _asegurar_4751(db, tenant_id):
            await audit_escribir(
                db,
                empresa_id=tenant_id,
                actor="system",
                action="SEED_PGC_4751",
                entity="account_plan",
                payload={"code": "4751"},
            )
            await db.flush()
        return 0

    creados = 0
    groups: dict[str, AccountPlan] = {}
    for code, name in GRUPOS:
        groups[code] = await _insertar(db, tenant_id, code, 1, name)
        creados += 1

    parents_n2: dict[str, AccountPlan] = {}
    for code, name in SUBGRUPOS:
        parents_n2[code] = await _insertar(db, tenant_id, code, 2, name, parent=groups[code[0]])
        creados += 1

    parents_n3: dict[str, AccountPlan] = {}
    for code, name in CUENTAS:
        parents_n3[code] = await _insertar(db, tenant_id, code, 3, name, parent=parents_n2[code[:2]])
        creados += 1

    for code, name, parent_code in SUBCUENTAS:
        await _insertar(
            db,
            tenant_id,
            code,
            4,
            name,
            parent=parents_n3[parent_code],
            is_selectable=True,
        )
        creados += 1

    await audit_escribir(
        db,
        empresa_id=tenant_id,
        actor="system",
        action="SEED_PGC",
        entity="account_plan",
        payload={
            "groups": len(GRUPOS),
            "subgroups": len(SUBGRUPOS),
            "accounts": len(CUENTAS),
            "subaccounts": len(SUBCUENTAS),
        },
    )
    await db.flush()
    return creados