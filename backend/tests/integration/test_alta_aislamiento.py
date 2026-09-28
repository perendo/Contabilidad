"""Tests SPEC-001 T025: aislamiento en alta de cuenta cross-tenant (US3)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.account_service import AccountError, crear_cuenta
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_alta_padre_otra_empresa_rechazado_403_404(db_session: AsyncSession) -> None:
    """Padre de otra empresa → AccountError parent_not_found (404)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Padre de empresa 1
    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre_1 is not None

    # Intentar crear en empresa 2 con padre de empresa 1
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 2, "43000001", "Cross tenant", padre_1.id)
    assert exc.value.code == "parent_not_found"


async def test_alta_codigo_duplicado_cross_tenant_permitido(db_session: AsyncSession) -> None:
    """Mismo código en distintas empresas SÍ se permite (unicidad por tenant)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Crear subcuenta 43000001 en empresa 1
    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    await crear_cuenta(db_session, 1, "43000001", "Cliente A", padre_1.id)

    # Crear mismo código en empresa 2 - debe funcionar
    padre_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    hija_2 = await crear_cuenta(db_session, 2, "43000001", "Cliente B", padre_2.id)

    assert hija_2.code == "43000001"
    assert hija_2.tenant_id == 2
    assert hija_2.parent_id == padre_2.id


async def test_alta_nunca_referencia_datos_otro_tenant(db_session: AsyncSession) -> None:
    """La alta nunca referencia datos de otro tenant (validación en servicio)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    # Verificar que el servicio valida tenant_id del padre
    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre_1 is not None

    # El servicio debe rechazar porque padre.tenant_id != tenant_id de la operación
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 2, "43000001", "Cross", padre_1.id)
    assert exc.value.code == "parent_not_found"


async def test_alta_crea_cuenta_solo_en_tenant_correcto(db_session: AsyncSession) -> None:
    """Cuenta creada solo existe en su tenant."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    hija_1 = await crear_cuenta(db_session, 1, "43000001", "Cliente 1", padre_1.id)

    # Verificar que no existe en tenant 2
    existe_en_2 = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == 2,
            AccountPlan.code == "43000001"
        )
    )
    assert existe_en_2 is None

    # Verificar que sí existe en tenant 1
    existe_en_1 = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == 1,
            AccountPlan.code == "43000001"
        )
    )
    assert existe_en_1 is not None
    assert existe_en_1.id == hija_1.id


async def test_alta_fk_compuesta_rechaza_cross_tenant_nivel_db(db_session: AsyncSession) -> None:
    """FK compuesta (tenant_id, parent_id) rechaza cross-tenant a nivel DB."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre_1 is not None

    # Insertar directamente en DB bypassando servicio
    cuenta_cross = AccountPlan(
        tenant_id=2,
        code="43000001",
        level=5,
        name="Cross DB",
        parent_id=padre_1.id,
        is_selectable=True,
    )
    db_session.add(cuenta_cross)

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_alta_multiples_empresas_aisladas(db_session: AsyncSession) -> None:
    """Múltiples empresas crean subcuentas independientemente."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)
    await _crear_empresa(db_session, 3)
    await seed_default_pgc(db_session, 3)

    # Crear subcuenta en cada empresa
    for tenant_id in [1, 2, 3]:
        padre = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == tenant_id, AccountPlan.code == "4300")
        )
        hija = await crear_cuenta(db_session, tenant_id, "43000001", f"Cliente {tenant_id}", padre.id)

        assert hija.tenant_id == tenant_id
        assert hija.code == "43000001"
        assert hija.parent_id == padre.id


async def test_alta_modificar_padre_no_afecta_otro_tenant(db_session: AsyncSession) -> None:
    """Crear hija en A no afecta selectable del padre en B."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)

    padre_1 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    padre_2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    assert padre_1 is not None and padre_2 is not None

    # Crear hija en empresa 1
    await crear_cuenta(db_session, 1, "43000001", "Cliente A", padre_1.id)
    await db_session.flush()

    # Padre en empresa 1 deja de ser selectable
    await db_session.refresh(padre_1)
    assert padre_1.is_selectable is False

    # Padre en empresa 2 sigue siendo selectable
    await db_session.refresh(padre_2)
    assert padre_2.is_selectable is True