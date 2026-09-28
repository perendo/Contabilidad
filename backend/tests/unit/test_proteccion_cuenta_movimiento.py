"""Tests SPEC-001 T031: protección de cuenta con movimientos (US4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.iam.company import Company
from services.acct.account_service import AccountError, actualizar_cuenta, crear_cuenta
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def _crear_asiento_con_linea(db: AsyncSession, tenant_id: int, account_id: int) -> JournalEntry:
    """Crear asiento POSTED con una línea en la cuenta dada."""
    asiento = JournalEntry(
        empresa_id=tenant_id,
        ejercicio=2026,
        fecha=date(2026, 1, 15),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Asiento de prueba",
        estado=JournalEntryEstado.POSTED,
        created_by="test",
    )
    db.add(asiento)
    await db.flush()

    linea = JournalEntryLine(
        empresa_id=tenant_id,
        journal_entry_id=asiento.id,
        account_id=account_id,
        cuenta="43000001",
        debe=Decimal("100.0000"),
        haber=Decimal("0.0000"),
        descripcion="Línea de prueba",
    )
    db.add(linea)

    # Línea de contrapartida para balancear - buscar una cuenta selectable distinta
    cuenta_contra = await db.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == tenant_id, AccountPlan.code == "5720")
    )
    if cuenta_contra:
        linea2 = JournalEntryLine(
            empresa_id=tenant_id,
            journal_entry_id=asiento.id,
            account_id=cuenta_contra.id,
            cuenta="5720",
            debe=Decimal("0.0000"),
            haber=Decimal("100.0000"),
            descripcion="Contrapartida",
        )
        db.add(linea2)

    await db.flush()
    return asiento


async def test_desactivar_cuenta_con_asientos_rechazado_409(db_session: AsyncSession) -> None:
    """Desactivar cuenta con imputaciones → AccountError account_has_entries (409)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "43000001")
    )
    # Si no existe 43000001, crear una subcuenta bajo 4300
    if cuenta is None:
        padre = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
        )
        cuenta = await crear_cuenta(db_session, 1, "43000001", "Cliente Test", padre.id)

    # Crear asiento con línea en esta cuenta
    await _crear_asiento_con_linea(db_session, 1, cuenta.id)

    # Intentar desactivar
    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db_session, 1, cuenta.id, is_active=False)
    assert exc.value.code == "account_has_entries"


async def test_trigger_db_bloquea_desactivar_con_asientos(db_session: AsyncSession) -> None:
    """Trigger DB chk_account_plan_protected bloquea UPDATE is_active true→false con asientos."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "43000001")
    )
    if cuenta is None:
        padre = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
        )
        cuenta = await crear_cuenta(db_session, 1, "43000001", "Cliente Test", padre.id)

    await _crear_asiento_con_linea(db_session, 1, cuenta.id)

    # Intentar UPDATE directo en DB (bypass servicio)
    cuenta.is_active = False

    with pytest.raises(Exception) as exc:  # IntegrityError o OperationalError por trigger
        await db_session.flush()

    # El trigger debe rechazar
    assert "no se puede desactivar una cuenta con asientos asociados" in str(exc.value).lower() \
        or "account_plan" in str(exc.value).lower()


async def test_borrar_cuenta_con_hijas_rechazado(db_session: AsyncSession) -> None:
    """Borrar cuenta con hijas → rechazado por trigger (API no expone DELETE, pero test defensivo)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None

    await crear_cuenta(db_session, 1, "43000001", "Cliente", padre.id)

    # Intentar borrar padre (tiene hija)
    await db_session.delete(padre)

    with pytest.raises(Exception) as exc:
        await db_session.flush()

    assert "tiene hijas" in str(exc.value).lower() or "account_plan" in str(exc.value).lower()


async def test_borrar_cuenta_con_asientos_rechazado(db_session: AsyncSession) -> None:
    """Borrar cuenta con asientos → rechazado por trigger."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "43000001")
    )
    if cuenta is None:
        padre = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
        )
        cuenta = await crear_cuenta(db_session, 1, "43000001", "Cliente Test", padre.id)

    await _crear_asiento_con_linea(db_session, 1, cuenta.id)

    await db_session.delete(cuenta)

    with pytest.raises(Exception) as exc:
        await db_session.flush()

    assert "imputaciones" in str(exc.value).lower() or "account_plan" in str(exc.value).lower()


async def test_editar_nombre_cuenta_con_asientos_permitido(db_session: AsyncSession) -> None:
    """Renombrar cuenta con asientos SÍ se permite (solo desactivar está protegido)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "43000001")
    )
    if cuenta is None:
        padre = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
        )
        cuenta = await crear_cuenta(db_session, 1, "43000001", "Cliente Test", padre.id)

    await _crear_asiento_con_linea(db_session, 1, cuenta.id)

    actualizada = await actualizar_cuenta(db_session, 1, cuenta.id, name="Cliente Renombrado")
    assert actualizada.name == "Cliente Renombrado"


async def test_reactivar_cuenta_inactiva_sin_asientos_permitido(db_session: AsyncSession) -> None:
    """Reactivar cuenta inactiva SIN asientos se permite."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "43000001")
    )
    if cuenta is None:
        padre = await db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
        )
        cuenta = await crear_cuenta(db_session, 1, "43000001", "Cliente Test", padre.id)

    # Desactivar SIN asientos (debe funcionar)
    await actualizar_cuenta(db_session, 1, cuenta.id, is_active=False)
    assert cuenta.is_active is False

    # Reactivar debe funcionar
    actualizada = await actualizar_cuenta(db_session, 1, cuenta.id, is_active=True)
    assert actualizada.is_active is True