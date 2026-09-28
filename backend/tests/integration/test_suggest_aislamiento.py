"""Tests SPEC-001 T018: suggest aislamiento cross-tenant (SC-001, SC-002)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.account_service import SuggestError, suggest
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_suggest_solo_apuntables_integracion(db_session: AsyncSession) -> None:
    """Solo cuentas is_selectable=true e is_active=true aparecen en suggest."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    items = await suggest(db_session, tenant_id=1, q="430")

    # Debe devolver solo la subcuenta 4300 (nivel 4, selectable)
    assert items, "debe devolver la subcuenta 4300"
    assert all(i["is_selectable"] and i["is_active"] for i in items)
    assert all(len(i["code"]) >= 4 for i in items)

    # Verificar que NO aparecen grupos (nivel 1), subgrupos (nivel 2), cuentas (nivel 3)
    # ni cuentas con hijas (nivel 4 con hijas)
    codes = {i["code"] for i in items}
    assert "430" not in codes  # nivel 3 - no selectable
    assert "43" not in codes   # nivel 2 - no selectable
    assert "4" not in codes    # nivel 1 - no selectable


async def test_suggest_por_nombre_integracion(db_session: AsyncSession) -> None:
    """Suggest por fragmento de nombre (pg_trgm) funciona."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    items = await suggest(db_session, tenant_id=1, q="Bancos")
    assert any(i["code"] == "5720" for i in items)  # "Bancos c/c vista euros"


async def test_suggest_por_prefijo_codigo(db_session: AsyncSession) -> None:
    """Suggest por prefijo de código funciona (indexado)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    items = await suggest(db_session, tenant_id=1, q="572")
    codes = {i["code"] for i in items}
    assert "5720" in codes  # Bancos c/c vista euros


async def test_suggest_sin_coincidencias_lista_vacia(db_session: AsyncSession) -> None:
    """Texto sin coincidencias devuelve lista vacía sin error (200)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    items = await suggest(db_session, tenant_id=1, q="zzzz")
    assert items == []


async def test_suggest_q_vacio_rechazado(db_session: AsyncSession) -> None:
    """Query vacío lanza SuggestError (validación 422 en endpoint)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    with pytest.raises(SuggestError):
        await suggest(db_session, tenant_id=1, q="")


async def test_suggest_aislamiento_cross_tenant(db_session: AsyncSession) -> None:
    """Empresa A no ve cuentas de Empresa B en suggest."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    items_a = await suggest(db_session, tenant_id=1, q="430")
    items_b = await suggest(db_session, tenant_id=2, q="430")

    # Cada empresa ve solo sus cuentas
    assert all(i["tenant_id"] == 1 for i in items_a)
    assert all(i["tenant_id"] == 2 for i in items_b)

    # Los IDs no se solapan (autoincremental por tenant)
    ids_a = {i["id"] for i in items_a}
    ids_b = {i["id"] for i in items_b}
    assert ids_a.isdisjoint(ids_b)


async def test_suggest_empresa_b_no_filtra_hacia_a(db_session: AsyncSession) -> None:
    """Datos coincidentes en B no se filtran hacia A."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Buscar algo que exista en ambas empresas
    items_a = await suggest(db_session, tenant_id=1, q="Cliente")
    items_b = await suggest(db_session, tenant_id=2, q="Cliente")

    # A ve solo sus "Clientes (euros)" 4300
    for item in items_a:
        assert item["tenant_id"] == 1
        assert item["code"] == "4300"

    # B ve solo sus "Clientes (euros)" 4300 (distinto ID)
    for item in items_b:
        assert item["tenant_id"] == 2
        assert item["code"] == "4300"


async def test_suggest_limit_respetado(db_session: AsyncSession) -> None:
    """Límite de resultados se respeta (máx 50)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # El seed tiene ~16 subcuentas nivel 4, probemos limit=5
    items = await suggest(db_session, tenant_id=1, q="4", limit=5)
    assert len(items) <= 5


async def test_suggest_cuentas_inactivas_excluidas(db_session: AsyncSession) -> None:
    """Cuentas inactivas (is_active=False) no aparecen en suggest."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Desactivar 4300
    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta is not None
    cuenta.is_active = False
    await db_session.flush()

    items = await suggest(db_session, tenant_id=1, q="430")
    assert items == []  # 4300 ya no aparece


async def test_suggest_cuentas_no_selectable_excluidas(db_session: AsyncSession) -> None:
    """Cuentas no selectable (con hijas) no aparecen en suggest."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # 430 (nivel 3) tiene hija 4300, por trigger no es selectable
    items = await suggest(db_session, tenant_id=1, q="430")
    codes = {i["code"] for i in items}
    assert "430" not in codes  # nivel 3 con hija -> no selectable
    assert "4300" in codes     # nivel 4 hoja -> selectable


async def test_suggest_limit_maximo_50(db_session: AsyncSession) -> None:
    """Límite máximo hardcodeado a 50 en el servicio."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # El servicio limita a 50 por defecto
    items = await suggest(db_session, tenant_id=1, q="4", limit=100)
    assert len(items) <= 50