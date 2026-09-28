"""T119: Test roundtrip multilínea (SPEC-006 US4).

Crear 3:2 → exportar CSV → importar de vuelta produce un asiento con el mismo
número de partidas (5) y el mismo balance.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from services.importexport.exportador import exportar_diario
from services.importexport.importador import importar_asientos
from services.journal.motor import crear_asiento_multilinea, listar_asientos
from tests.conftest import sembrar_empresa_pgc

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Compra"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Alquiler"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldo"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Prov A"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Prov B"},
]


async def test_roundtrip_conserva_partidas_y_balance(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="Gastos septiembre", lineas=LINEAS_3_2,
    )
    await db_session.flush()

    contenido, _, _ = await exportar_diario(
        db_session, empresa_id=10,
        fecha_desde=date(2026, 9, 1), fecha_hasta=date(2026, 9, 30),
        formato="csv",
    )

    importado = await importar_asientos(
        db_session, empresa_id=10, file_bytes=contenido,
        nombre="diario_roundtrip.csv", actor="tester",
    )
    await db_session.flush()
    assert importado["asientos_importados"] == 1
    assert importado["omisiones"] == []

    listado = await listar_asientos(db_session, empresa_id=10)
    assert listado["total"] == 2
    importado_item = next(i for i in listado["items"] if i["n_lineas"] == 5)
    assert importado_item["total_debe"] == "500.0000"
    assert importado_item["total_haber"] == "500.0000"

    lineas = list(
        (
            await db_session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == uuid.UUID(importado_item["id"])
                )
            )
        ).all()
    )
    assert len(lineas) == 5
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    assert debe == haber == Decimal("500.0000")