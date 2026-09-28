"""Tests SPEC-001 T012: aislamiento del árbol (SC-001)."""

from __future__ import annotations

from sqlalchemy import select
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


async def test_arbol_empresa_a_no_contiene_nodos_de_b(db_session: AsyncSession) -> None:
    """Cargar 2 empresas con cuentas, el árbol de A no devuelve nodos de B."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    arbol_a = await build_tree(db_session, 1)

    # Recopilar todos los IDs del árbol A
    ids_a = set()
    def recopilar(nodos: list[dict]) -> None:
        for n in nodos:
            ids_a.add(n["id"])
            recopilar(n["children"])

    recopilar(arbol_a)

    # Verificar que ningún ID del árbol A existe en la empresa B
    for id_a in ids_a:
        cuenta_en_b = await obtener_cuenta(db_session, 2, id_a)
        assert cuenta_en_b is None, f"ID {id_a} de A encontrado en B"


async def test_get_by_id_cross_tenant_devuelve_none(db_session: AsyncSession) -> None:
    """GET por ID de cuenta de B desde sesión de A devuelve None (no filtra datos)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Obtener una cuenta de la empresa 2
    cuenta_b = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    assert cuenta_b is not None

    # Consultar desde empresa 1
    resultado = await obtener_cuenta(db_session, 1, cuenta_b.id)
    assert resultado is None


async def test_suggest_cross_tenant_aislado(db_session: AsyncSession) -> None:
    """Suggest de A no expone cuentas de B."""
    from services.acct.account_service import suggest

    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    items_a = await suggest(db_session, tenant_id=1, q="430")
    items_b = await suggest(db_session, tenant_id=2, q="430")

    # Cada empresa ve solo sus cuentas
    for item in items_a:
        assert item["tenant_id"] == 1
    for item in items_b:
        assert item["tenant_id"] == 2

    # Los IDs no se solapan
    ids_a = {item["id"] for item in items_a}
    ids_b = {item["id"] for item in items_b}
    assert ids_a.isdisjoint(ids_b)


async def test_cuentas_mismo_codigo_distintas_empresas(db_session: AsyncSession) -> None:
    """Mismo código en distintas empresas son entidades distintas."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    cuenta_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )

    assert cuenta_1 is not None
    assert cuenta_2 is not None
    assert cuenta_1.id != cuenta_2.id
    assert cuenta_1.tenant_id == 1
    assert cuenta_2.tenant_id == 2


async def test_arbol_vacio_empresa_sin_seed(db_session: AsyncSession) -> None:
    """Empresa sin seed devuelve árbol vacío, no datos de otra empresa."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    # Empresa 2 SIN seed

    arbol_2 = await build_tree(db_session, 2)
    assert arbol_2 == []

    # Verificar que no se filtraron datos de la empresa 1
    arbol_1 = await build_tree(db_session, 1)
    assert len(arbol_1) > 0


async def test_contar_nodos_por_empresa_aislado(db_session: AsyncSession) -> None:
    """El conteo de nodos por empresa está completamente aislado."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    arbol_1 = await build_tree(db_session, 1)
    arbol_2 = await build_tree(db_session, 2)

    def contar(nodos: list[dict]) -> int:
        total = len(nodos)
        for n in nodos:
            total += contar(n["children"])
        return total

    count_1 = contar(arbol_1)
    count_2 = contar(arbol_2)

    assert count_1 == count_2  # Mismo seed, mismo conteo
    assert count_1 > 0


async def test_modificar_cuenta_no_afecta_otra_empresa(db_session: AsyncSession) -> None:
    """Modificar cuenta en A no afecta cuenta con mismo código en B."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Modificar nombre en empresa 1
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None
    nombre_original = cuenta_1.name
    cuenta_1.name = "Clientes MODIFICADO"
    await db_session.flush()

    # Verificar que empresa 2 no cambió
    cuenta_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    assert cuenta_2 is not None
    assert cuenta_2.name == nombre_original
    assert cuenta_2.name != "Clientes MODIFICADO"


async def test_desactivar_cuenta_no_afecta_otra_empresa(db_session: AsyncSession) -> None:
    """Desactivar cuenta en A no afecta cuenta en B."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Desactivar en empresa 1
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None
    cuenta_1.is_active = False
    await db_session.flush()

    # Verificar que empresa 2 sigue activa
    cuenta_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    assert cuenta_2 is not None
    assert cuenta_2.is_active is True