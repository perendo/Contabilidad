"""Tests SPEC-001 T032: aislamiento en edición de cuenta cross-tenant (US4)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.account_service import AccountError, actualizar_cuenta
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_editar_cuenta_otra_empresa_rechazado_404(db_session: AsyncSession) -> None:
    """PATCH sobre cuenta de otra empresa → AccountError not_found (404)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Cuenta de empresa 1
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None

    # Intentar editar desde contexto de empresa 2
    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db_session, 2, cuenta_1.id, name="Hack")
    assert exc.value.code == "not_found"


async def test_editar_nombre_no_filtra_datos_otra_empresa(db_session: AsyncSession) -> None:
    """Editar nombre en A no afecta cuenta con mismo código en B."""
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
    assert cuenta_1 is not None and cuenta_2 is not None
    nombre_original = cuenta_2.name

    # Editar en empresa 1
    await actualizar_cuenta(db_session, 1, cuenta_1.id, name="Clientes MODIFICADO")
    await db_session.flush()

    # Verificar que empresa 2 no cambió
    await db_session.refresh(cuenta_2)
    assert cuenta_2.name == nombre_original
    assert cuenta_2.name != "Clientes MODIFICADO"


async def test_editar_estado_no_filtra_datos_otra_empresa(db_session: AsyncSession) -> None:
    """Desactivar en A no afecta estado en B."""
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
    assert cuenta_1 is not None and cuenta_2 is not None

    # Desactivar en empresa 1
    await actualizar_cuenta(db_session, 1, cuenta_1.id, is_active=False)
    await db_session.flush()

    # Verificar que empresa 2 sigue activa
    await db_session.refresh(cuenta_2)
    assert cuenta_2.is_active is True


async def test_editar_cuenta_inexistente_en_tenant_rechazado(db_session: AsyncSession) -> None:
    """Cuenta que existe en otro tenant pero no en el actual → not_found."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Obtener ID de cuenta de empresa 1
    cuenta_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta_1 is not None

    # Intentar editar en empresa 2 usando ID de empresa 1
    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db_session, 2, cuenta_1.id, name="Intento hack")
    assert exc.value.code == "not_found"


async def test_editar_nombre_duplicado_cross_tenant_permitido(db_session: AsyncSession) -> None:
    """Renombrar a nombre que existe en OTRA empresa SÍ se permite."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Usar un nombre que existe en tenant 1 pero NO en tenant 2
    nombre_exclusivo_tenant1 = "Nombre Exclusivo Tenant 1"
    
    # Crear una cuenta en tenant 1 con nombre exclusivo
    from services.acct.account_service import crear_cuenta
    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    await crear_cuenta(db_session, 1, "43000099", nombre_exclusivo_tenant1, padre_1.id)

    # En tenant 2, 4300 = "Clientes (euros)"
    cuenta_4300_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    assert cuenta_4300_2 is not None

    # Renombrar 4300 en tenant 2 al nombre exclusivo de tenant 1 - DEBE PERMITIRSE
    # (unicidad es por tenant, no global)
    actualizada = await actualizar_cuenta(db_session, 2, cuenta_4300_2.id, name=nombre_exclusivo_tenant1)
    assert actualizada.name == nombre_exclusivo_tenant1


async def test_editar_multiple_cuentas_aisladas(db_session: AsyncSession) -> None:
    """Múltiples ediciones en distintas empresas no se interfieren."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)
    await _crear_empresa(db_session, 3)
    await seed_default_pgc(db_session, 3)

    # Editar 4300 en cada empresa con nombre diferente
    for tenant_id, sufijo in [(1, "Uno"), (2, "Dos"), (3, "Tres")]:
        cuenta = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == tenant_id, AccountPlan.code == "4300")
        )
        await actualizar_cuenta(db_session, tenant_id, cuenta.id, name=f"Clientes {sufijo}")

    # Verificar cada una
    for tenant_id, sufijo in [(1, "Uno"), (2, "Dos"), (3, "Tres")]:
        cuenta = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == tenant_id, AccountPlan.code == "4300")
        )
        assert cuenta.name == f"Clientes {sufijo}"