"""T118: Test importación multilínea (SPEC-006 US4).

El importador de SPEC-005 agrupa las filas por `numero_asiento` y pasa la
lista completa de líneas al motor: un grupo 3:2 se importa como un único
asiento con 5 líneas y balance correcto.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from services.importexport.importador import importar_asientos
from services.journal.motor import listar_asientos
from tests.conftest import sembrar_empresa_pgc

CSV_MULTILINEA = (
    "fecha;numero_asiento;concepto;cuenta;debe;haber;detalle\n"
    "2026-09-01;G1;Varios gastos;6000;300.0000;0.0000;Compra\n"
    "2026-09-01;G1;Varios gastos;6210;150.0000;0.0000;Alquiler\n"
    "2026-09-01;G1;Varios gastos;6400;50.0000;0.0000;Sueldo\n"
    "2026-09-01;G1;Varios gastos;4000;0.0000;400.0000;Proveedor A\n"
    "2026-09-01;G1;Varios gastos;4100;0.0000;100.0000;Proveedor B\n"
)


async def test_importa_grupo_3_2_completo(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    resultado = await importar_asientos(
        db_session,
        empresa_id=10,
        file_bytes=CSV_MULTILINEA.encode("utf-8-sig"),
        nombre="multilinea.csv",
        actor="tester",
    )
    await db_session.flush()

    assert resultado["asientos_importados"] == 1
    assert resultado["asientos_omitidos"] == 0
    assert resultado["omisiones"] == []

    listado = await listar_asientos(db_session, empresa_id=10)
    assert listado["total"] == 1
    item = listado["items"][0]
    assert item["n_lineas"] == 5
    assert item["total_debe"] == "500.0000"
    assert item["total_haber"] == "500.0000"

    lineas = list(
        (
            await db_session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == uuid.UUID(item["id"])
                )
            )
        ).all()
    )
    assert len(lineas) == 5
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    assert debe == haber == Decimal("500.0000")