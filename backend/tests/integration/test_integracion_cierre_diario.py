"""Tests SPEC-004 Polish (T051): regularización/cierre en la secuencia del diario."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntryEstado, JournalEntryTipo
from services.closing.close_year import cerrar_ejercicio
from services.journal.entry_service import asentar, crear_borrador
from services.reports.ledger import ledger
from services.reports.trial_balance import trial_balance
from tests.conftest import crear_empresa


async def test_cierre_integrado_en_diario_y_balance(db_session: AsyncSession) -> None:
    await crear_empresa(db_session, 10, nif="T00000010", razon_social="Empresa 10 SL")
    await db_session.flush()
    ids: dict[str, int] = {}
    for codigo in (
        "1", "12", "129", "5", "57", "572", "5720",
        "6", "60", "600", "6000", "7", "70", "700", "7000",
    ):
        cuenta = AccountPlan(
            tenant_id=10, code=codigo, name=f"C-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=True,
        )
        db_session.add(cuenta)
        await db_session.flush()
        ids[codigo] = cuenta.id
    db_session.add(
        FiscalYear(
            empresa_id=10, year=2026,
            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31),
        )
    )
    await db_session.flush()

    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 5, 1), concepto="V",
        lineas=[
            {"account_id": ids["6000"], "debit": "80.0000", "credit": "0"},
            {"account_id": ids["5720"], "debit": "0", "credit": "80.0000"},
        ],
        actor="test",
    )
    primero = await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="test")
    assert primero.numero_asiento == 1

    resultado = await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    assert resultado["regularizacion_entry_id"] is not None
    assert resultado["cierre_entry_id"] is not None

    balance = await trial_balance(
        db_session, empresa_id=10,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), level=4,
    )
    assert balance["cuadra"] is True
    saldos = {i["code"]: i["saldo"] for i in balance["items"]}
    assert saldos.get("6000") == "0.0000"
    assert saldos.get("1290") == "0.0000"

    mayor = await ledger(
        db_session,
        empresa_id=10,
        account_id=await db_session.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == 10, AccountPlan.code == "1290"
            )
        ),
    )
    assert mayor["saldo_final"] == "0.0000"
    assert all(e is not None for e in (primero.numero_asiento,))
    assert primero.estado == JournalEntryEstado.POSTED
    assert primero.tipo == JournalEntryTipo.GENERAL
