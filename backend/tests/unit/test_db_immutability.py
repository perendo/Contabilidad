"""DB-level immutability (constitución II).

Verifica que los triggers de base de datos rechacen UPDATE/DELETE sobre
asientos POSTED/CANCELLED, sus líneas y el log de auditoría (WORM). Los triggers
instalados en SQLite replican las migraciones PostgreSQL
`backend/migrations/000_audit_log.sql` y `003_journal.sql`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.audit.audit_log import AuditLog


async def _asiento_posted(db_session, empresa_id: int) -> JournalEntry:
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=2026,
        fecha=date(2026, 9, 17),
        tipo=JournalEntryTipo.COBRO,
        concepto="cobro",
        estado=JournalEntryEstado.POSTED,
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    db_session.add(asiento)
    db_session.add_all(
        [
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                cuenta="572",
                debe=Decimal("100.0000"),
                haber=Decimal("0.0000"),
            ),
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                cuenta="430",
                debe=Decimal("0.0000"),
                haber=Decimal("100.0000"),
            ),
        ]
    )
    await db_session.flush()
    return asiento


async def test_update_posted_journal_entry_rechazado(db_session):
    asiento = await _asiento_posted(db_session, 31)
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("UPDATE journal_entry SET concepto = 'alterado' WHERE id = :id"),
            {"id": asiento.id.hex},
        )
    await db_session.rollback()


async def test_delete_posted_journal_entry_rechazado(db_session):
    asiento = await _asiento_posted(db_session, 32)
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM journal_entry WHERE id = :id"),
            {"id": asiento.id.hex},
        )
    await db_session.rollback()


async def test_update_linea_de_asiento_posted_rechazado(db_session):
    asiento = await _asiento_posted(db_session, 33)
    linea = await db_session.scalar(
        select(JournalEntryLine).where(
            JournalEntryLine.journal_entry_id == asiento.id
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("UPDATE journal_entry_line SET debe = 1 WHERE id = :id"),
            {"id": linea.id.hex},
        )
    await db_session.rollback()


async def test_delete_linea_de_asiento_posted_rechazado(db_session):
    asiento = await _asiento_posted(db_session, 34)
    linea = await db_session.scalar(
        select(JournalEntryLine).where(
            JournalEntryLine.journal_entry_id == asiento.id
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM journal_entry_line WHERE id = :id"),
            {"id": linea.id.hex},
        )
    await db_session.rollback()


async def test_draft_a_posted_si_permitido(db_session):
    asiento = JournalEntry(
        empresa_id=35,
        ejercicio=2026,
        fecha=date(2026, 9, 17),
        tipo=JournalEntryTipo.GENERAL,
        concepto="borrador",
        estado=JournalEntryEstado.DRAFT,
    )
    db_session.add(asiento)
    await db_session.flush()
    db_session.add_all(
        [
            JournalEntryLine(
                empresa_id=35,
                journal_entry_id=asiento.id,
                cuenta="572",
                debe=Decimal("100.0000"),
                haber=Decimal("0.0000"),
            ),
            JournalEntryLine(
                empresa_id=35,
                journal_entry_id=asiento.id,
                cuenta="430",
                debe=Decimal("0.0000"),
                haber=Decimal("100.0000"),
            ),
        ]
    )
    await db_session.flush()
    asiento.estado = JournalEntryEstado.POSTED
    await db_session.flush()
    assert asiento.estado is JournalEntryEstado.POSTED


async def test_draft_a_posted_desbalanceado_rechazado(db_session):
    asiento = JournalEntry(
        empresa_id=38,
        ejercicio=2026,
        fecha=date(2026, 9, 17),
        tipo=JournalEntryTipo.GENERAL,
        concepto="desbalanceado",
        estado=JournalEntryEstado.DRAFT,
    )
    db_session.add(asiento)
    await db_session.flush()
    db_session.add(
        JournalEntryLine(
            empresa_id=38,
            journal_entry_id=asiento.id,
            cuenta="572",
            debe=Decimal("100.0000"),
            haber=Decimal("0.0000"),
        )
    )
    await db_session.flush()
    asiento.estado = JournalEntryEstado.POSTED
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_update_audit_log_rechazado(db_session):
    registro = AuditLog(empresa_id=36, operacion="TEST", entidad="test")
    db_session.add(registro)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("UPDATE audit_log SET operacion = 'ALTERADO' WHERE id = :id"),
            {"id": registro.id.hex},
        )
    await db_session.rollback()


async def test_delete_audit_log_rechazado(db_session):
    registro = AuditLog(empresa_id=37, operacion="TEST", entidad="test")
    db_session.add(registro)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM audit_log WHERE id = :id"),
            {"id": registro.id.hex},
        )
    await db_session.rollback()
