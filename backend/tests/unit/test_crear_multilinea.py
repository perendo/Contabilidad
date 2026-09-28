"""T006: Test creación multilínea balanceada (SPEC-006 US1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Compra"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Alquiler"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldo"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Proveedor A"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Proveedor B"},
]


async def test_creacion_3_2_persiste_5_lineas(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    entrada = await crear_asiento_multilinea(
        db_session,
        empresa_id=10,
        fecha=date(2026, 9, 1),
        concepto="Varios gastos",
        lineas=LINEAS_3_2,
    )
    await db_session.flush()

    assert entrada.estado.value == "POSTED"
    assert entrada.numero_asiento == 1

    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entrada.id)
        )
    ).all()
    assert len(list(lineas)) == 5
    total_debe = sum((l.debe for l in lineas), Decimal(0))
    total_haber = sum((l.haber for l in lineas), Decimal(0))
    assert total_debe == Decimal("500.0000")
    assert total_haber == Decimal("500.0000")