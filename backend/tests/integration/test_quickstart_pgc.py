"""Tests SPEC-001 T039: escenarios quickstart del plan (5 escenarios)."""

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
from services.acct.account_service import (
    AccountError,
    actualizar_cuenta,
    crear_cuenta,
    suggest,
)
from services.acct.plan_tree import build_tree, obtener_cuenta
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def _imputar(db: AsyncSession, tenant_id: int, account_id: int) -> None:
    asiento = JournalEntry(
        empresa_id=tenant_id,
        ejercicio=2026,
        fecha=date(2026, 1, 15),
        tipo=JournalEntryTipo.GENERAL,
        concepto="quickstart",
        estado=JournalEntryEstado.POSTED,
        created_by="test",
    )
    db.add(asiento)
    await db.flush()
    contra = await db.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == tenant_id, AccountPlan.code == "5720")
    )
    db.add_all(
        [
            JournalEntryLine(
                empresa_id=tenant_id,
                journal_entry_id=asiento.id,
                account_id=account_id,
                cuenta="43000001",
                debe=Decimal("100.0000"),
                haber=Decimal("0.0000"),
            ),
            JournalEntryLine(
                empresa_id=tenant_id,
                journal_entry_id=asiento.id,
                account_id=contra.id,
                cuenta="5720",
                debe=Decimal("0.0000"),
                haber=Decimal("100.0000"),
            ),
        ]
    )
    await db.flush()


async def test_scenario1_seed_y_arbol(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    creados = await seed_default_pgc(db_session, 1)
    assert creados > 0
    grupos = (
        await db_session.scalars(
            select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.level == 1)
        )
    ).all()
    assert len(grupos) == 7
    hojas = (
        await db_session.scalars(
            select(AccountPlan).where(
                AccountPlan.tenant_id == 1,
                AccountPlan.level == 4,
                AccountPlan.is_selectable.is_(True),
            )
        )
    ).all()
    assert hojas
    arbol = await build_tree(db_session, 1)
    assert len(arbol) == 7
    assert await seed_default_pgc(db_session, 1) == 0


async def test_scenario2_suggest(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)
    items = await suggest(db_session, 1, q="430")
    assert items and all(i["is_selectable"] and i["tenant_id"] == 1 for i in items)
    assert await suggest(db_session, 1, q="zzzz") == []


async def test_scenario3_alta(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    hija = await crear_cuenta(db_session, 1, "43000001", "Cliente Acme S.L.", padre.id)
    assert (hija.level, hija.is_selectable) == (5, True)
    await db_session.refresh(padre)
    assert padre.is_selectable is False
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "43000001", "Duplicado", padre.id)
    assert exc.value.code == "code_duplicate"
    with pytest.raises(AccountError):
        await crear_cuenta(db_session, 1, "430000011", "Larga", padre.id)


async def test_scenario4_edicion_y_proteccion(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    editada = await actualizar_cuenta(db_session, 1, cuenta.id, is_active=False)
    assert editada.is_active is False
    await actualizar_cuenta(db_session, 1, cuenta.id, is_active=True)

    padre = cuenta
    hija = await crear_cuenta(db_session, 1, "43000001", "Cliente", padre.id)
    await _imputar(db_session, 1, hija.id)
    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db_session, 1, hija.id, is_active=False)
    assert exc.value.code == "account_has_entries"


async def test_scenario5_aislamiento(db_session: AsyncSession) -> None:
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    await _crear_empresa(db_session, 2)
    await seed_default_pgc(db_session, 2)
    cuenta_b = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 2, AccountPlan.code == "4300")
    )
    arbol_a = await build_tree(db_session, 1)
    ids_a = {n["id"] for n in arbol_a}
    assert cuenta_b.id not in ids_a
    assert await obtener_cuenta(db_session, 1, cuenta_b.id) is None
    with pytest.raises(AccountError) as exc:
        await actualizar_cuenta(db_session, 1, cuenta_b.id, name="hack")
    assert exc.value.code == "not_found"
