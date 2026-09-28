"""Tests SPEC-001 T023: alta de subcuenta correcta (US3)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.account_service import crear_cuenta
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_alta_subcuenta_hereda_jerarquia(db_session: AsyncSession) -> None:
    """level = padre + 1, prefijo del padre, apuntabilidad de la nueva hoja."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Padre: 4300 (nivel 4, selectable)
    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None
    assert padre.level == 4
    assert padre.is_selectable is True

    # Crear hija nivel 5
    hija = await crear_cuenta(db_session, 1, "43000001", "Cliente Acme S.L.", padre.id)

    assert hija.level == 5
    assert hija.code == "43000001"
    assert hija.parent_id == padre.id
    assert hija.code.startswith(padre.code)
    assert hija.is_selectable is True  # hoja nivel 5


async def test_alta_subcuenta_madre_deja_de_ser_apuntable(db_session: AsyncSession) -> None:
    """Al crear hija, la madre pasa a is_selectable=False (trigger DB)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None
    assert padre.is_selectable is True

    await crear_cuenta(db_session, 1, "43000001", "Cliente Acme S.L.", padre.id)
    await db_session.flush()

    # Recargar padre
    await db_session.refresh(padre)
    assert padre.is_selectable is False


async def test_alta_cuenta_nivel1_sin_padre(db_session: AsyncSession) -> None:
    """Cuenta nivel 1 (grupo) se crea sin padre."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Crear grupo adicional
    grupo = await crear_cuenta(db_session, 1, "8", "Grupo Extra", None)

    assert grupo.level == 1
    assert grupo.parent_id is None
    assert grupo.is_selectable is False  # nivel 1 nunca selectable


async def test_alta_subcuenta_nivel2_bajo_nivel1(db_session: AsyncSession) -> None:
    """Subgrupo nivel 2 bajo grupo nivel 1."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    grupo = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "1")
    )
    assert grupo is not None

    subgrupo = await crear_cuenta(db_session, 1, "18", "Subgrupo Extra", grupo.id)

    assert subgrupo.level == 2
    assert subgrupo.parent_id == grupo.id
    assert subgrupo.code.startswith(grupo.code)
    assert subgrupo.is_selectable is False  # nivel 2 nunca selectable


async def test_alta_cuenta_nivel3_bajo_nivel2(db_session: AsyncSession) -> None:
    """Cuenta nivel 3 bajo subgrupo nivel 2."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    subgrupo = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "11")
    )
    assert subgrupo is not None

    cuenta = await crear_cuenta(db_session, 1, "118", "Cuenta Extra", subgrupo.id)

    assert cuenta.level == 3
    assert cuenta.parent_id == subgrupo.id
    assert cuenta.code.startswith(subgrupo.code)
    assert cuenta.is_selectable is False  # nivel 3 nunca selectable


async def test_alta_subcuenta_nivel4_bajo_nivel3(db_session: AsyncSession) -> None:
    """Subcuenta nivel 4 (hoja apuntable) bajo cuenta nivel 3."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta_n3 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "111")
    )
    assert cuenta_n3 is not None

    subcuenta = await crear_cuenta(db_session, 1, "1118", "Subcuenta Extra", cuenta_n3.id)

    assert subcuenta.level == 4
    assert subcuenta.parent_id == cuenta_n3.id
    assert subcuenta.code.startswith(cuenta_n3.code)
    assert subcuenta.is_selectable is True  # hoja nivel 4 = apuntable


async def test_alta_multiples_hijos_mismo_padre(db_session: AsyncSession) -> None:
    """Múltiples hijos bajo el mismo padre."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None

    h1 = await crear_cuenta(db_session, 1, "43000001", "Cliente A", padre.id)
    h2 = await crear_cuenta(db_session, 1, "43000002", "Cliente B", padre.id)

    assert h1.code == "43000001"
    assert h2.code == "43000002"
    assert h1.parent_id == h2.parent_id == padre.id
    assert h1.is_selectable is True
    assert h2.is_selectable is True

    # Padre sigue no selectable
    await db_session.refresh(padre)
    assert padre.is_selectable is False