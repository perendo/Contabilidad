"""T110: Test anulación balanceada (SPEC-006 US3).

El rectificativo está balanceado (Debe == Haber) y la suma neta
rectificativo + original == 0 en cada cuenta.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from services.journal.anulador import anular_asiento
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc

LINEAS = [
    {"cuenta": "6000", "debe": "100.0000", "haber": "0.0000"},
    {"cuenta": "6210", "debe": "50.0000", "haber": "0.0000"},
    {"cuenta": "5720", "debe": "0.0000", "haber": "150.0000"},
]


async def _lineas(db_session, entry_id):
    return list(
        (
            await db_session.scalars(
                select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
            )
        ).all()
    )


async def test_rectificativo_balanceado_y_neta_cero(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    original = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="Compra", lineas=LINEAS
    )
    await db_session.flush()

    respuesta = await anular_asiento(db_session, empresa_id=10, entry_id=original.id)
    await db_session.flush()

    reversal_id = uuid.UUID(respuesta["asiento_rectificativo"]["id"])
    orig = list(await _lineas(db_session, original.id))
    rev = list(await _lineas(db_session, reversal_id))

    suma_rev_debe = sum((l.debe for l in rev), Decimal(0))
    suma_rev_haber = sum((l.haber for l in rev), Decimal(0))
    assert suma_rev_debe == suma_rev_haber

    netas: dict = {}
    for l in orig:
        netas[l.cuenta] = netas.get(l.cuenta, Decimal(0)) + l.debe - l.haber
    for l in rev:
        netas[l.cuenta] = netas.get(l.cuenta, Decimal(0)) + l.debe - l.haber
    for cuenta, saldo in netas.items():
        assert saldo == 0, f"Cuenta {cuenta} con saldo neto {saldo}"

    rev_detalle = respuesta["asiento_rectificativo"]
    assert rev_detalle["total_debe"] == rev_detalle["total_haber"]