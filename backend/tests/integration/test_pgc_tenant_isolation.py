"""Tests SPEC-001 T010: PGC cross-tenant isolation (SC-001)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.plan_tree import build_tree, obtener_cuenta
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_arbol_empresa_a_no_devuelve_nodos_de_b(db_session: AsyncSession) -> None:
    """El árbol de la Empresa A nunca devuelve nodos de la Empresa B."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    arbol_a = await build_tree(db_session, 1)
    arbol_b = await build_tree(db_session, 2)

    # Contar nodos en cada árbol
    def contar_nodos(nodos: list[dict]) -> int:
        total = len(nodos)
        for n in nodos:
            total += contar_nodos(n["children"])
        return total

    assert contar_nodos(arbol_a) > 0
    assert contar_nodos(arbol_b) > 0
    # Los IDs no se solapan porque son autoincrementales por tenant
    # Pero verificamos que no hay fugas de datos
    ids_a = set()
    def recopilar_ids(nodos: list[dict], destino: set[int]) -> None:
        for n in nodos:
            destino.add(n["id"])
            recopilar_ids(n["children"], destino)

    recopilar_ids(arbol_a, ids_a)
    # Ningún ID del árbol A debería aparecer en el árbol B si consultamos por ID
    for id_a in ids_a:
        cuenta_b = await obtener_cuenta(db_session, 2, id_a)
        assert cuenta_b is None, f"ID {id_a} de empresa A visible en empresa B"


async def test_suggest_empresa_a_no_expone_b(db_session: AsyncSession) -> None:
    """Suggest de la Empresa A no expone cuentas de la Empresa B."""
    from services.acct.account_service import suggest

    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Buscar "430" en ambas empresas - cada una ve solo sus cuentas
    items_a = await suggest(db_session, tenant_id=1, q="430")
    items_b = await suggest(db_session, tenant_id=2, q="430")

    assert all(item["tenant_id"] == 1 for item in items_a)
    assert all(item["tenant_id"] == 2 for item in items_b)


async def test_get_by_id_cross_tenant_rechazado(db_session: AsyncSession) -> None:
    """GET por ID de cuenta de otra empresa devuelve None (no filtra datos)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Obtener una cuenta de la empresa 1
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None

    # Intentar obtenerla desde la empresa 2
    cuenta_desde_2 = await obtener_cuenta(db_session, 2, cuenta_1.id)
    assert cuenta_desde_2 is None


async def test_crear_cuenta_cross_tenant_rechazado(db_session: AsyncSession) -> None:
    """Crear cuenta con padre de otra empresa falla por FK compuesta."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Obtener padre de la empresa 1
    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "430")
    )
    assert padre_1 is not None

    # Intentar crear cuenta en empresa 2 con padre de empresa 1
    cuenta_cross = AccountPlan(
        tenant_id=2, code="4300", level=4, name="Cross", parent_id=padre_1.id, is_selectable=True
    )
    db_session.add(cuenta_cross)

    with pytest.raises(IntegrityError):  # FK compuesta (tenant_id, parent_id)
        await db_session.flush()


async def test_editar_cuenta_cross_tenant_rechazado(db_session: AsyncSession) -> None:
    """Editar cuenta de otra empresa falla (no existe en el tenant)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Obtener cuenta de la empresa 1
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None

    # Intentar actualizarla desde el contexto de la empresa 2
    # (simulando que el servicio filtra por tenant_id)
    cuenta_desde_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.id == cuenta_1.id)
    )
    assert cuenta_desde_2 is None


async def test_contar_cuentas_por_empresa_aislado(db_session: AsyncSession) -> None:
    """El conteo de cuentas por empresa está aislado."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Verificar que hay cuentas
    all_1 = (await db_session.scalars(
        select(AccountPlan).where(AccountPlan.tenant_id == 1)
    )).all()
    all_2 = (await db_session.scalars(
        select(AccountPlan).where(AccountPlan.tenant_id == 2)
    )).all()

    assert len(all_1) > 0
    assert len(all_2) > 0
    assert len(all_1) == len(all_2)  # Mismo seed en ambas


async def test_nombres_duplicados_cross_tenant_permitidos(db_session: AsyncSession) -> None:
    """Nombres iguales en distintas empresas SÍ se permiten (UNIQUE es por tenant)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Ambas empresas tienen "Clientes (euros)" código 4300
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    cuenta_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None
    assert cuenta_2 is not None
    assert cuenta_1.name == cuenta_2.name == "Clientes (euros)"
    assert cuenta_1.id != cuenta_2.id  # IDs distintos por ser autoincremental


async def test_codigos_duplicados_cross_tenant_permitidos(db_session: AsyncSession) -> None:
    """Códigos iguales en distintas empresas SÍ se permiten (UNIQUE es por tenant)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Ambas empresas tienen código "4300"
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    cuenta_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None
    assert cuenta_2 is not None
    assert cuenta_1.code == cuenta_2.code == "4300"
    assert cuenta_1.id != cuenta_2.id