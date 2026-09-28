"""Correlatividad de numeracion del asiento de apertura (SPEC-009 T011, FR-004/005)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from conftest import sembrar_empresa_pgc
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado
from services.cycle.apertura import generar_asiento_apertura
from services.journal.entry_service import asentar, crear_borrador


async def _ids(db, empresa_id) -> dict[str, int]:
    return {
        code: ident
        for code, ident in (
            await db.execute(
                select(AccountPlan.code, AccountPlan.id).where(
                    AccountPlan.tenant_id == empresa_id,
                    AccountPlan.is_active.is_(True),
                )
            )
        ).all()
    }


async def _cerrar_deja_saldo(db, empresa_id, year):
    ids = await _ids(db, empresa_id)
    entry = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=year,
        fecha=date(year, 6, 30),
        tipo=JournalEntryTipo.GENERAL,
        concepto=f"Saldos {year}",
        estado=JournalEntryEstado.POSTED,
        numero_asiento=1,
    )
    db.add(entry)
    await db.flush()
    db.add(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=entry.id,
            account_id=ids["1110"],
            line_no=1,
            cuenta="1110",
            debe=Decimal("0.0000"),
            haber=Decimal("5000.0000"),
        )
    )
    db.add(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=entry.id,
            account_id=ids["2100"],
            line_no=2,
            cuenta="2100",
            debe=Decimal("5000.0000"),
            haber=Decimal("0.0000"),
        )
    )
    db.add(
        FiscalYear(
            empresa_id=empresa_id,
            year=year,
            date_start=date(year, 1, 1),
            date_end=date(year, 12, 31),
            is_closed=True,
            cierre_entry_id=None,
        )
    )
    await db.flush()


async def _destino(db, empresa_id, year):
    db.add(
        EjercicioContable(
            empresa_id=empresa_id,
            ejercicio=year,
            fecha_inicio=date(year, 1, 1),
            fecha_fin=date(year, 12, 31),
            estado=EjercicioEstado.abierto,
        )
    )
    await db.flush()


async def test_primer_asiento_del_ejercicio(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _cerrar_deja_saldo(db_session, 10, 2026)
    await _destino(db_session, 10, 2027)
    await db_session.flush()

    resultado = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    assert resultado["numero_asiento"] == 1


async def test_sigue_a_avisar_asiento_existente(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _cerrar_deja_saldo(db_session, 10, 2026)
    await _destino(db_session, 10, 2027)
    await db_session.flush()

    ids = await _ids(db_session, 10)
    borrador = await crear_borrador(
        db_session,
        empresa_id=10,
        fecha=date(2027, 1, 3),
        concepto="Asiento manual previo a la apertura",
        lineas=[
            {"account_id": ids["5720"], "debit": "500.0000", "credit": "0"},
            {"account_id": ids["7000"], "debit": "0", "credit": "500.0000"},
        ],
    )
    await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="ana")

    resultado = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    assert resultado["numero_asiento"] == 2

    numeros = (
        await db_session.scalars(
            select(JournalEntry.numero_asiento).where(
                JournalEntry.empresa_id == 10,
                JournalEntry.ejercicio == 2027,
                JournalEntry.estado == JournalEntryEstado.POSTED,
            )
        )
    ).all()
    assert sorted(numeros) == [1, 2]