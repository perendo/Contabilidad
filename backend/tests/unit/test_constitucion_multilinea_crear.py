"""T103: Tests constitución V US1 (SPEC-006).

Todo asiento creado a través del motor debe quedar balanceado (partida doble);
el motor nunca persiste un asiento desbalanceado, para cualquier combinación
de partidas (1:1, 2:1, 3:2) y para cualquier empresa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


async def _totalizar(db_session, entry_id) -> tuple[Decimal, Decimal]:
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    return debe, haber


async def test_varios_tipos_siempre_balanceados(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    escenarios = [
        {"cuenta": "6000", "debe": "100.0000", "haber": "0.0000"},
        {"cuenta": "5720", "debe": "0.0000", "haber": "100.0000"},
    ]
    e1 = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="1:1", lineas=escenarios,
    )
    e2 = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="2:1",
        lineas=[
            {"cuenta": "6000", "debe": "80.0000", "haber": "0.0000"},
            {"cuenta": "6210", "debe": "20.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "100.0000"},
        ],
    )
    e3 = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="3:2",
        lineas=[
            {"cuenta": "6000", "debe": "50.0000", "haber": "0.0000"},
            {"cuenta": "6210", "debe": "30.0000", "haber": "0.0000"},
            {"cuenta": "6400", "debe": "20.0000", "haber": "0.0000"},
            {"cuenta": "4000", "debe": "0.0000", "haber": "60.0000"},
            {"cuenta": "4100", "debe": "0.0000", "haber": "40.0000"},
        ],
    )
    await db_session.flush()

    for entry in (e1, e2, e3):
        debe, haber = await _totalizar(db_session, entry.id)
        assert debe == haber, f"Asiento {entry.id} desbalanceado"


async def test_empresa_20_tambien_balanceada(db_session):
    await sembrar_empresa_pgc(db_session, 20)
    entry = await crear_asiento_multilinea(
        db_session, empresa_id=20, fecha=date(2026, 9, 1),
        concepto="B",
        lineas=[
            {"cuenta": "6000", "debe": "10.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "10.0000"},
        ],
    )
    await db_session.flush()
    assert entry.empresa_id == 20
    debe, haber = await _totalizar(db_session, entry.id)
    assert debe == haber