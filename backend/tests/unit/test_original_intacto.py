"""T111: Test original intacto (SPEC-006 US3).

La anulación nunca modifica el asiento original (constitución II): concepto,
fecha, estado y líneas permanecen idénticos tras crear el rectificativo.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine
from services.journal.anulador import anular_asiento
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc

LINEAS = [
    {"cuenta": "6000", "debe": "250.0000", "haber": "0.0000", "detalle": "Mercancías"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "250.0000", "detalle": "Proveedor"},
]


async def test_original_no_modificado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    original = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="Compra aplazada", lineas=LINEAS,
    )
    await db_session.flush()

    antes = {
        "concepto": original.concepto,
        "fecha": original.fecha,
        "tipo": original.tipo.value,
        "original_id": None,
        "numero_asiento": original.numero_asiento,
    }
    lineas_antes = sorted(
        (l.cuenta, l.debe, l.haber, l.descripcion)
        for l in await _lineas(db_session, original.id)
    )

    await anular_asiento(db_session, empresa_id=10, entry_id=original.id, actor="tester")
    await db_session.flush()

    despues = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == original.id)
    )
    lineas_despues = sorted(
        (l.cuenta, l.debe, l.haber, l.descripcion)
        for l in await _lineas(db_session, original.id)
    )

    assert despues.concepto == antes["concepto"]
    assert despues.fecha == antes["fecha"]
    assert despues.estado.value == "CANCELLED"
    assert despues.tipo.value == antes["tipo"]
    assert despues.original_id is None
    assert despues.numero_asiento == antes["numero_asiento"]
    assert lineas_despues == lineas_antes


async def _lineas(db_session, entry_id):
    return list(
        (
            await db_session.scalars(
                select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
            )
        ).all()
    )