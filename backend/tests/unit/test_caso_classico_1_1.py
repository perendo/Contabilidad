"""T104: Test caso clásico 1:1 (SPEC-006 US2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


async def test_caso_clasico_1_1(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    entrada = await crear_asiento_multilinea(
        db_session,
        empresa_id=10,
        fecha=date(2026, 9, 1),
        concepto="Compra al contado",
        lineas=[
            {"cuenta": "6000", "debe": "250.0000", "haber": "0.0000", "detalle": "Mercancías"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "250.0000", "detalle": "Banco"},
        ],
    )
    await db_session.flush()

    assert entrada.numero_asiento == 1
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entrada.id)
        )
    ).all()
    assert len(list(lineas)) == 2
    total_debe = sum((l.debe for l in lineas), Decimal(0))
    total_haber = sum((l.haber for l in lineas), Decimal(0))
    assert total_debe == total_haber == Decimal("250.0000")


async def test_siguiente_numero_correlativo(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    e1 = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="Uno",
        lineas=[
            {"cuenta": "6000", "debe": "1.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "1.0000"},
        ],
    )
    e2 = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="Dos",
        lineas=[
            {"cuenta": "6210", "debe": "2.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "2.0000"},
        ],
    )
    await db_session.flush()
    assert e1.numero_asiento == 1
    assert e2.numero_asiento == 2