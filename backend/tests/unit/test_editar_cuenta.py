"""Tests SPEC-001 T030: edición correcta de cuenta (US4)."""

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


async def test_editar_nombre_cuenta_sin_movimientos(db_session: AsyncSession) -> None:
    """Renombrar cuenta sin asientos persiste correctamente."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta is not None
    nombre_original = cuenta.name

    actualizada = await actualizar_cuenta(db_session, 1, cuenta.id, name="Clientes Nacionales")

    assert actualizada.name == "Clientes Nacionales"
    assert actualizada.name != nombre_original
    assert actualizada.id == cuenta.id


async def test_editar_activar_cuenta_inactiva(db_session: AsyncSession) -> None:
    """Activar cuenta inactiva sin asientos persiste."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta is not None
    cuenta.is_active = False
    await db_session.flush()

    actualizada = await actualizar_cuenta(db_session, 1, cuenta.id, is_active=True)

    assert actualizada.is_active is True


async def test_editar_desactivar_cuenta_activa_sin_movimientos(db_session: AsyncSession) -> None:
    """Desactivar cuenta activa sin asientos persiste."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta is not None
    assert cuenta.is_active is True

    actualizada = await actualizar_cuenta(db_session, 1, cuenta.id, is_active=False)

    assert actualizada.is_active is False


async def test_editar_nombre_y_estado_simultaneamente(db_session: AsyncSession) -> None:
    """Cambiar nombre y estado en una sola operación."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta is not None

    actualizada = await actualizar_cuenta(db_session, 1, cuenta.id, name="Nuevo Nombre", is_active=False)

    assert actualizada.name == "Nuevo Nombre"
    assert actualizada.is_active is False


async def test_editar_nombre_duplicado_rechazado_409(db_session: AsyncSession) -> None:
    """Renombrar a nombre ya existente en la empresa → AccountError name_duplicate."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # 4300 = "Clientes (euros)", 4100 = "Acreedores por prestaciones de servicios"
    cuenta_4300 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    cuenta_4100 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4100")
    )
    assert cuenta_4300 is not None and cuenta_4100 is not None

    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db_session, 1, cuenta_4300.id, name=cuenta_4100.name)
    assert exc.value.code == "name_duplicate"


async def test_editar_sin_cambios_retorna_misma_cuenta(db_session: AsyncSession) -> None:
    """Sin cambios (name=None, is_active=None) retorna la cuenta sin modificar."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta is not None

    actualizada = await actualizar_cuenta(db_session, 1, cuenta.id, name=None, is_active=None)

    assert actualizada.id == cuenta.id
    assert actualizada.name == cuenta.name
    assert actualizada.is_active == cuenta.is_active


async def test_editar_cuenta_inexistente_rechazado_404(db_session: AsyncSession) -> None:
    """Cuenta inexistente en el tenant → AccountError not_found."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db_session, 1, 999999, name="Nuevo")
    assert exc.value.code == "not_found"