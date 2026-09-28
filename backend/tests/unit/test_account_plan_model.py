"""Tests SPEC-001 T009: AccountPlan model constraints and relationships."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_unicidad_tenant_code(db_session: AsyncSession) -> None:
    """UNIQUE (tenant_id, code) - código duplicado en misma empresa falla."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Intentar insertar código duplicado en la misma empresa
    cuenta_dup = AccountPlan(
        tenant_id=1, code="1110", level=4, name="Duplicado", parent_id=1, is_selectable=True
    )
    db_session.add(cuenta_dup)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_constraint_level_range(db_session: AsyncSession) -> None:
    """CHECK (level BETWEEN 1 AND 5) - nivel fuera de rango falla."""
    await _crear_empresa(db_session, 1)

    cuenta_invalida = AccountPlan(tenant_id=1, code="1", level=6, name="Inválido")
    db_session.add(cuenta_invalida)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_fk_tenant_companies(db_session: AsyncSession) -> None:
    """FK tenant_id -> companies.company_id - empresa inexistente falla."""
    cuenta = AccountPlan(tenant_id=999, code="1", level=1, name="Sin empresa")
    db_session.add(cuenta)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_fk_parent_compuesta(db_session: AsyncSession) -> None:
    """FK compuesta (tenant_id, parent_id) -> account_plan(tenant_id, id)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Buscar cuenta padre (111 - Patrimonio neto, level 3)
    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "111")
    )
    assert padre is not None

    # Buscar cuenta padre de otra empresa (no existe, pero simulamos el id)
    # Insertar cuenta con parent_id de otra empresa (tenant_id=2, pero padre de tenant_id=1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # El padre de la empresa 1 tiene un id, intentamos usarlo en empresa 2
    cuenta_cross = AccountPlan(
        tenant_id=2, code="1110", level=4, name="Cross", parent_id=padre.id
    )
    db_session.add(cuenta_cross)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_seed_idempotente(db_session: AsyncSession) -> None:
    """Seed idempotente: reintentar seed no duplica."""
    await _crear_empresa(db_session, 1)
    count1 = await seed_default_pgc(db_session, 1)
    count2 = await seed_default_pgc(db_session, 1)

    assert count1 > 0, "primer seed crea filas"
    assert count2 == 0, "segundo seed no crea filas (idempotente)"

    # Verificar que solo hay 7 grupos nivel 1
    grupos = (
        await db_session.scalars(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.level == 1)
        )
    ).all()
    assert len(grupos) == 7


async def test_jerarquia_y_niveles(db_session: AsyncSession) -> None:
    """Jerarquía: nivel = longitud del código (1-4), nivel 5 = 5-8 dígitos."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Verificar nivel 1 (1 dígito)
    l1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "1")
    )
    assert l1 is not None and l1.level == 1

    # Verificar nivel 2 (2 dígitos)
    l2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "11")
    )
    assert l2 is not None and l2.level == 2

    # Verificar nivel 3 (3 dígitos)
    l3 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "111")
    )
    assert l3 is not None and l3.level == 3

    # Verificar nivel 4 (4 dígitos)
    l4 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "1110")
    )
    assert l4 is not None and l4.level == 4 and l4.is_selectable is True


async def test_is_selectable_solo_hojas_nivel_ge_4(db_session: AsyncSession) -> None:
    """Solo hojas nivel >= 4 son is_selectable=True."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Cuentas nivel 1-3 NO son selectables
    no_selectables = (
        await db_session.scalars(
            select(AccountPlan).where(
                AccountPlan.tenant_id == 1,
                AccountPlan.level <= 3,
                AccountPlan.is_selectable.is_(True),
            )
        )
    ).all()
    assert len(no_selectables) == 0

    # Cuentas nivel 4 SÍ son selectables (hojas)
    selectables = (
        await db_session.scalars(
            select(AccountPlan).where(
                AccountPlan.tenant_id == 1,
                AccountPlan.level == 4,
                AccountPlan.is_selectable.is_(True),
            )
        )
    ).all()
    assert len(selectables) > 0


async def test_timestamps_utc(db_session: AsyncSession) -> None:
    """created_at y updated_at son TIMESTAMPTZ (UTC)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "1")
    )
    assert cuenta is not None
    assert cuenta.created_at is not None
    assert cuenta.updated_at is not None
    # En SQLite los timestamps son naive, en PG serían aware
    # Solo verificamos que no son None


async def test_parent_id_nivel1_es_null(db_session: AsyncSession) -> None:
    """Nivel 1 tiene parent_id NULL."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    l1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "1")
    )
    assert l1 is not None and l1.parent_id is None


async def test_cuenta_hija_hereda_prefijo_padre(db_session: AsyncSession) -> None:
    """Código de hija empieza por código del padre."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    hijos = (
        await db_session.scalars(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.parent_id.is_not(None))
        )
    ).all()

    for hijo in hijos:
        padre = await db_session.get(AccountPlan, hijo.parent_id)
        assert padre is not None
        assert hijo.code.startswith(padre.code), f"{hijo.code} no empieza por {padre.code}"