"""T109: Test anulación invertida (SPEC-006 US3).

Un asiento 3:2 se anula con un rectificativo 2:3: las líneas originales se
invierten (Debe ⇄ Haber) y el rectificativo compensa el original.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine
from services.journal.anulador import anular_asiento
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Compra"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Alquiler"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldo"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Prov A"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Prov B"},
]


async def _lineas(db_session, entry_id):
    return list(
        (
            await db_session.scalars(
                select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
            )
        ).all()
    )


async def test_rectificativo_invierte_lineas(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    original = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="Gastos de septiembre", lineas=LINEAS_3_2,
    )
    await db_session.flush()

    respuesta = await anular_asiento(
        db_session, empresa_id=10, entry_id=original.id, actor="tester"
    )
    await db_session.flush()

    reversal_id = uuid.UUID(respuesta["asiento_rectificativo"]["id"])
    assert respuesta["asiento_original_id"] == str(original.id)

    orig = list(await _lineas(db_session, original.id))
    rev = list(await _lineas(db_session, reversal_id))

    assert len(rev) == 5
    for lo, lr in zip(sorted(orig, key=lambda x: x.cuenta), sorted(rev, key=lambda x: x.cuenta)):
        assert lr.cuenta == lo.cuenta
        assert lr.debe == lo.haber
        assert lr.haber == lo.debe

    orig_debe = 3
    orig_haber = 2
    rev_debe = sum(1 for l in rev if l.debe > 0)
    rev_haber = sum(1 for l in rev if l.haber > 0)
    assert orig_debe == 3 and orig_haber == 2
    assert rev_debe == orig_haber
    assert rev_haber == orig_debe

    reversal = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == reversal_id)
    )
    assert reversal.tipo.value == "REVERSAL"
    assert reversal.estado.value == "POSTED"
    assert reversal.original_id == original.id