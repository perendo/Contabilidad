"""Tests SPEC-004 Polish (T047): constitución V en flujos de informes y cierre."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryEstado
from models.iam.company import Company
from services.closing.close_year import cerrar_ejercicio
from services.journal.entry_service import AsientoError, asentar, crear_borrador
from services.reports.trial_balance import trial_balance


async def _pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    db.add(
        Company(company_id=tenant_id, nif=f"T{tenant_id:08d}", razon_social="E SL")
    )
    await db.flush()
    ids: dict[str, int] = {}
    for codigo in (
        "1", "12", "129", "5", "57", "572", "5720",
        "6", "60", "600", "6000", "7", "70", "700", "7000",
    ):
        cuenta = AccountPlan(
            tenant_id=tenant_id, code=codigo, name=f"C-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=True,
        )
        db.add(cuenta)
        await db.flush()
        ids[codigo] = cuenta.id
    return ids


async def test_balance_cuadra_y_sin_float(db_session: AsyncSession) -> None:
    c = await _pgc(db_session, 10)
    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 4, 1), concepto="V",
        lineas=[
            {"account_id": c["6000"], "debit": "33.3333", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "33.3333"},
        ],
        actor="test",
    )
    await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="test")
    balance = await trial_balance(
        db_session, empresa_id=10,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), level=4,
    )
    assert balance["cuadra"] is True
    for item in balance["items"]:
        for campo in ("debe", "haber", "saldo"):
            assert isinstance(item[campo], str)
            assert Decimal(item[campo]).as_tuple().exponent >= -4


async def test_cierre_posted_inmutable_y_bloquea(db_session: AsyncSession) -> None:
    c = await _pgc(db_session, 10)
    db_session.add(
        FiscalYear(
            empresa_id=10, year=2026,
            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31),
        )
    )
    await db_session.flush()
    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 4, 1), concepto="V",
        lineas=[
            {"account_id": c["6000"], "debit": "10.0000", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "10.0000"},
        ],
        actor="test",
    )
    await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="test")
    resultado = await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    reg = await db_session.get(JournalEntry, UUID(resultado["regularizacion_entry_id"]))
    assert reg is not None and reg.estado == JournalEntryEstado.POSTED
    with pytest.raises(AsientoError) as exc:
        await crear_borrador(
            db_session, empresa_id=10, fecha=date(2026, 4, 2), concepto="X",
            lineas=[
                {"account_id": c["6000"], "debit": "1.0000", "credit": "0"},
                {"account_id": c["5720"], "debit": "0", "credit": "1.0000"},
            ],
            actor="test",
        )
    assert exc.value.code == "ejercicio_cerrado"
