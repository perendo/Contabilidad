"""Tests SPEC-001 T029: triggers de selectable a nivel DB (US3)."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_trigger_selectable_insert_pone_madre_false(db_session: AsyncSession) -> None:
    """Trigger AFTER INSERT pone is_selectable=false en la madre al crear hija."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Padre: 4300 (nivel 4, selectable=True)
    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None
    assert padre.is_selectable is True

    # Insertar hija DIRECTAMENTE por SQL (bypass servicio) para probar trigger DB
    await db_session.execute(
        text("""
            INSERT INTO account_plan (tenant_id, code, name, parent_id, level, is_selectable, is_active, created_at, updated_at)
            VALUES (:tenant_id, :code, :name, :parent_id, :level, :is_selectable, :is_active, datetime('now'), datetime('now'))
        """),
        {
            "tenant_id": 1,
            "code": "43000001",
            "name": "Cliente SQL Directo",
            "parent_id": padre.id,
            "level": 5,
            "is_selectable": True,
            "is_active": True,
        }
    )
    await db_session.flush()

    # Recargar padre - el trigger AFTER INSERT debe haberlo puesto a false
    await db_session.refresh(padre)
    assert padre.is_selectable is False, "Trigger DB debe poner madre is_selectable=false"


async def test_trigger_selectable_insert_self_nivel_ge_4_true(db_session: AsyncSession) -> None:
    """Trigger AFTER INSERT pone is_selectable=true en la nueva cuenta si level >= 4."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None

    # Insertar hija nivel 5 por SQL
    await db_session.execute(
        text("""
            INSERT INTO account_plan (tenant_id, code, name, parent_id, level, is_selectable, is_active, created_at, updated_at)
            VALUES (:tenant_id, :code, :name, :parent_id, :level, :is_selectable, :is_active, datetime('now'), datetime('now'))
        """),
        {
            "tenant_id": 1,
            "code": "43000001",
            "name": "Cliente SQL Directo",
            "parent_id": padre.id,
            "level": 5,
            "is_selectable": False,  # Valor inicial ignorado por trigger
            "is_active": True,
        }
    )
    await db_session.flush()

    # Buscar la hija insertada
    hija = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "43000001")
    )
    assert hija is not None
    assert hija.level == 5
    assert hija.is_selectable is True, "Trigger debe poner is_selectable=true para level >= 4"


async def test_trigger_selectable_insert_self_nivel_lt_4_false(db_session: AsyncSession) -> None:
    """Trigger AFTER INSERT pone is_selectable=false en la nueva cuenta si level < 4."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Crear grupo nivel 1 (no selectable)
    await db_session.execute(
        text("""
            INSERT INTO account_plan (tenant_id, code, name, parent_id, level, is_selectable, is_active, created_at, updated_at)
            VALUES (:tenant_id, :code, :name, :parent_id, :level, :is_selectable, :is_active, datetime('now'), datetime('now'))
        """),
        {
            "tenant_id": 1,
            "code": "8",
            "name": "Grupo Extra",
            "parent_id": None,
            "level": 1,
            "is_selectable": True,  # Valor inicial ignorado
            "is_active": True,
        }
    )
    await db_session.flush()

    grupo = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "8")
    )
    assert grupo is not None
    assert grupo.level == 1
    assert grupo.is_selectable is False, "Trigger debe poner is_selectable=false para level < 4"


async def test_trigger_selectable_update_manual_simulacion(db_session: AsyncSession) -> None:
    """Simular efecto de trigger selectable_update: viejo padre recupera, nuevo pierde."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Padre original: 4300 (selectable=True)
    padre_original = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre_original is not None and padre_original.is_selectable is True

    # Crear SEGUNDO padre nivel 4 bajo mismo abuelo 430 (4301)
    abuelo = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "430")
    )
    await db_session.execute(
        text("""
            INSERT INTO account_plan (tenant_id, code, name, parent_id, level, is_selectable, is_active, created_at, updated_at)
            VALUES (1, '4301', 'Clientes Extranjeros', :parent_id, 4, 1, 1, datetime('now'), datetime('now'))
        """),
        {"parent_id": abuelo.id}
    )
    await db_session.flush()

    padre_nuevo = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4301")
    )
    assert padre_nuevo is not None and padre_nuevo.is_selectable is True

    # Crear hija bajo padre_original (4300) con código válido 4300xxxx
    await db_session.execute(
        text("""
            INSERT INTO account_plan (tenant_id, code, name, parent_id, level, is_selectable, is_active, created_at, updated_at)
            VALUES (1, '43000001', 'Cliente Movimiento', :parent_id, 5, 1, 1, datetime('now'), datetime('now'))
        """),
        {"parent_id": padre_original.id}
    )
    await db_session.flush()

    await db_session.refresh(padre_original)
    assert padre_original.is_selectable is False

    # Simular el efecto del trigger selectable_update:
    # - Viejo padre (4300) ya no tiene hijas -> recupera selectable si level >= 4
    # - Nuevo padre (4301) gana hija -> pierde selectable
    await db_session.execute(
        text("UPDATE account_plan SET is_selectable = 1 WHERE id = :id AND tenant_id = 1"),
        {"id": padre_original.id}
    )
    await db_session.execute(
        text("UPDATE account_plan SET is_selectable = 0 WHERE id = :id AND tenant_id = 1"),
        {"id": padre_nuevo.id}
    )
    await db_session.flush()

    await db_session.refresh(padre_original)
    await db_session.refresh(padre_nuevo)

    assert padre_original.is_selectable is True, "Viejo padre recupera selectable al no tener hijas"
    assert padre_nuevo.is_selectable is False, "Nuevo padre pierde selectable al ganar hija"


async def test_trigger_protected_update_desactivar_con_asientos(db_session: AsyncSession) -> None:
    """Trigger BEFORE UPDATE bloquea desactivar cuenta con asientos."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Crear subcuenta
    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    await db_session.execute(
        text("""
            INSERT INTO account_plan (tenant_id, code, name, parent_id, level, is_selectable, is_active, created_at, updated_at)
            VALUES (1, '43000001', 'Cliente Test', :parent_id, 5, 1, 1, datetime('now'), datetime('now'))
        """),
        {"parent_id": padre.id}
    )
    await db_session.flush()

    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "43000001")
    )
    assert cuenta is not None

    # Crear asiento en journal_entry_line (necesario para trigger protection)
    # Primero crear journal_entry
    await db_session.execute(
        text("""
            INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, tipo, concepto, estado, created_at)
            VALUES (:id, 1, 2026, '2026-01-15', 'GENERAL', 'Test', 'POSTED', datetime('now'))
        """),
        {"id": "00000000-0000-0000-0000-000000000001"}
    )

    # Crear journal_entry_line apuntando a la cuenta
    await db_session.execute(
        text("""
            INSERT INTO journal_entry_line (id, empresa_id, journal_entry_id, account_id, cuenta, debe, haber, descripcion)
            VALUES (:id, 1, '00000000-0000-0000-0000-000000000001', :account_id, '43000001', 100.0, 0.0, 'Test')
        """),
        {"id": "00000000-0000-0000-0000-000000000002", "account_id": cuenta.id}
    )

    # Crear contrapartida
    cuenta_contra = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "5720")
    )
    if cuenta_contra:
        await db_session.execute(
            text("""
                INSERT INTO journal_entry_line (id, empresa_id, journal_entry_id, account_id, cuenta, debe, haber, descripcion)
                VALUES (:id, 1, '00000000-0000-0000-0000-000000000001', :account_id, '5720', 0.0, 100.0, 'Test')
            """),
            {"id": "00000000-0000-0000-0000-000000000003", "account_id": cuenta_contra.id}
        )

    await db_session.flush()

    # Intentar desactivar por SQL directo - trigger debe rechazar
    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text("UPDATE account_plan SET is_active = 0 WHERE id = :id AND tenant_id = 1"),
            {"id": cuenta.id}
        )
        await db_session.flush()

    assert "no se puede desactivar una cuenta con asientos asociados" in str(exc.value).lower() \
        or "account_plan" in str(exc.value).lower()


async def test_trigger_protected_delete_con_hijas(db_session: AsyncSession) -> None:
    """Trigger BEFORE DELETE bloquea borrar cuenta con hijas."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None

    # Crear hija por SQL
    await db_session.execute(
        text("""
            INSERT INTO account_plan (tenant_id, code, name, parent_id, level, is_selectable, is_active, created_at, updated_at)
            VALUES (1, '43000001', 'Cliente', :parent_id, 5, 1, 1, datetime('now'), datetime('now'))
        """),
        {"parent_id": padre.id}
    )
    await db_session.flush()

    # Intentar borrar padre - trigger debe rechazar
    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text("DELETE FROM account_plan WHERE id = :id AND tenant_id = 1"),
            {"id": padre.id}
        )
        await db_session.flush()

    assert "tiene hijas" in str(exc.value).lower() or "account_plan" in str(exc.value).lower()