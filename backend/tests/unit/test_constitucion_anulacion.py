"""T116: Tests constitución V US3 (SPEC-006).

La anulación es inmutable: el original no se actualiza ni se borra (constitución
II), el rectificativo es un `JournalEntry` nuevo balanceado, y un UPDATE directo
sobre un asiento POSTED se rechaza a nivel de base de datos.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry, JournalEntryLine
from services.journal.anulador import anular_asiento
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc

LINEAS = [
    {"cuenta": "6000", "debe": "100.0000", "haber": "0.0000"},
    {"cuenta": "5720", "debe": "0.0000", "haber": "100.0000"},
]


async def _totales(db_session, entry_id) -> tuple[Decimal, Decimal]:
    lineas = list(
        (
            await db_session.scalars(
                select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
            )
        ).all()
    )
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    return debe, haber


async def test_rectificativo_es_entrada_nueva_balanceada(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    original = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="Compra", lineas=LINEAS
    )
    await db_session.flush()

    respuesta = await anular_asiento(db_session, empresa_id=10, entry_id=original.id)
    await db_session.flush()

    reversal_id = uuid.UUID(respuesta["asiento_rectificativo"]["id"])
    assert str(reversal_id) != str(original.id)

    contados = await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.id.in_([original.id, reversal_id]),
            JournalEntry.estado == "POSTED",
        )
    )
    assert contados is not None
    for entry_id in (original.id, reversal_id):
        debe, haber = await _totales(db_session, entry_id)
        assert debe == haber


async def test_update_directo_a_posted_rechazado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    original = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="Compra", lineas=LINEAS
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        await db_session.execute(
            update(JournalEntry)
            .where(JournalEntry.id == original.id)
            .values(concepto="Modificado")
        )
        await db_session.flush()

    intacto = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == original.id)
    )
    assert intacto.concepto == "Compra"


async def test_delete_directo_a_posted_rechazado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    original = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="Compra", lineas=LINEAS
    )
    await db_session.flush()

    with pytest.raises(IntegrityError) as exc_info:
        await db_session.delete(original)
        await db_session.flush()
    assert "inmutable" in str(exc_info.value)
    await db_session.rollback()