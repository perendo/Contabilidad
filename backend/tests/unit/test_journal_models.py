"""Unit tests SPEC-002 T010: constraints del modelo journal (SQLite real)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.acct.journal_sequence import SecuenciaAsiento


async def _entrada(db, empresa_id: int = 10, numero: int | None = None) -> JournalEntry:
    entrada = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=2026,
        fecha=__import__("datetime").date(2026, 1, 15),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Venta",
        estado=JournalEntryEstado.POSTED,
        numero_asiento=numero,
        created_by="Ana",
    )
    if entrada.id is None:
        entrada.id = uuid.uuid4()
    db.add(entrada)
    await db.flush()
    return entrada


async def test_numero_unico_por_empresa_ejercicio(motor_db_session):
    await _entrada(motor_db_session, numero=1)
    with pytest.raises(IntegrityError):
        await _entrada(motor_db_session, numero=1)
    await motor_db_session.rollback()


async def test_numero_independiente_por_empresa(motor_db_session):
    await _entrada(motor_db_session, empresa_id=10, numero=1)
    await motor_db_session.rollback()
    await _entrada(motor_db_session, empresa_id=20, numero=1)
    await motor_db_session.flush()


async def test_linea_debe_xor_haber(motor_db_session):
    entrada = await _entrada(motor_db_session)
    db = motor_db_session
    db.add(
        JournalEntryLine(
            empresa_id=entrada.empresa_id,
            journal_entry_id=entrada.id,
            line_no=1,
            cuenta="4300",
            debe=10,
            haber=10,
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_linea_sin_importe_rechazada(motor_db_session):
    entrada = await _entrada(motor_db_session)
    db = motor_db_session
    db.add(
        JournalEntryLine(
            empresa_id=entrada.empresa_id,
            journal_entry_id=entrada.id,
            line_no=1,
            cuenta="4300",
            debe=0,
            haber=0,
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_linea_fk_compuesta_empresa(motor_db_session):
    entrada_a = await _entrada(motor_db_session, empresa_id=10)
    db = motor_db_session
    db.add(
        JournalEntryLine(
            empresa_id=20,
            journal_entry_id=entrada_a.id,
            line_no=1,
            cuenta="4300",
            debe=10,
            haber=0,
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_linea_fk_entry_inexistente(motor_db_session):
    db = motor_db_session
    db.add(
        JournalEntryLine(
            empresa_id=10,
            journal_entry_id=uuid.uuid4(),
            line_no=1,
            cuenta="4300",
            debe=10,
            haber=0,
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_secuencia_unicidad_par(motor_db_session):
    db = motor_db_session
    db.add(SecuenciaAsiento(empresa_id=10, ejercicio=2026, ultimo_numero=1))
    await db.flush()
    db.add(SecuenciaAsiento(empresa_id=10, ejercicio=2026, ultimo_numero=2))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


async def test_secuencia_por_empresa_independiente(motor_db_session):
    db = motor_db_session
    db.add(SecuenciaAsiento(empresa_id=10, ejercicio=2026, ultimo_numero=1))
    await db.flush()
    db.add(SecuenciaAsiento(empresa_id=20, ejercicio=2026, ultimo_numero=1))
    await db.flush()


async def test_importes_numero_decimal(motor_db_session):
    """Los importes se leen como Decimal, nunca float."""
    entrada = await _entrada(motor_db_session)
    db = motor_db_session
    db.add(
        JournalEntryLine(
            empresa_id=entrada.empresa_id,
            journal_entry_id=entrada.id,
            line_no=1,
            cuenta="4300",
            debe="100.0000",
            haber="0",
        )
    )
    db.add(
        JournalEntryLine(
            empresa_id=entrada.empresa_id,
            journal_entry_id=entrada.id,
            line_no=2,
            cuenta="5720",
            debe="0",
            haber="100.0000",
        )
    )
    await db.flush()
    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entrada.id)
        )
    ).all()
    assert all(type(l.debe) is not float and type(l.haber) is not float for l in lineas)