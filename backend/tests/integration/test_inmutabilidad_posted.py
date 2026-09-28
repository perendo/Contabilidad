"""Integration tests SPEC-002 T030: inmutabilidad de POSTED/CANCELLED (US3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntryEstado


def _entry_id(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Inmutable")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200
    return entry_id


async def test_update_raw_posted_denegado(journal_api):
    entry_id = uuid.UUID(_entry_id(journal_api))

    async def _intentar(s):
        await s.execute(
            text("UPDATE journal_entry SET concepto='Hack' WHERE id=:id"),
            {"id": entry_id.hex},
        )

    with pytest.raises(IntegrityError):
        await journal_api.consultar(_intentar)


async def test_delete_raw_posted_denegado(journal_api):
    entry_id = uuid.UUID(_entry_id(journal_api))

    async def _intentar(s):
        await s.execute(
            text("DELETE FROM journal_entry WHERE id=:id"),
            {"id": entry_id.hex},
        )

    with pytest.raises(IntegrityError):
        await journal_api.consultar(_intentar)


async def test_delete_raw_linea_posted_denegado(journal_api):
    entry_id = uuid.UUID(_entry_id(journal_api))

    async def _intentar(s):
        fila_id = (
            await s.execute(
                text(
                    "SELECT id FROM journal_entry_line"
                    " WHERE journal_entry_id=:id LIMIT 1"
                ),
                {"id": entry_id.hex},
            )
        ).scalar_one()
        await s.execute(text("DELETE FROM journal_entry_line WHERE id=:lid"), {"lid": fila_id})

    with pytest.raises(IntegrityError):
        await journal_api.consultar(_intentar)


async def test_cancelled_tambien_inmutable(journal_api):
    entry_id = _entry_id(journal_api)
    assert journal_api.anular(entry_id).status_code == 201
    original_id = uuid.UUID(entry_id)

    async def _intentar(s):
        await s.execute(
            text("UPDATE journal_entry SET fecha='2026-12-01' WHERE id=:id"),
            {"id": original_id.hex},
        )

    with pytest.raises(IntegrityError):
        await journal_api.consultar(_intentar)


async def test_no_hay_endpoints_update_delete(journal_api):
    entry_id = _entry_id(journal_api)
    assert journal_api.client.delete(f"/api/v1/journal/entries/{entry_id}").status_code == 405
    assert journal_api.client.patch(f"/api/v1/journal/entries/{entry_id}").status_code == 405


async def test_orm_update_posted_denegado(journal_api):
    """Modificar atributos de un POSTED cargado vía ORM → IntegrityError."""
    from sqlalchemy import select

    from models.acct.journal import JournalEntry

    entry_id = uuid.UUID(_entry_id(journal_api))

    async def _intentar(s):
        entrada = await s.scalar(select(JournalEntry).where(JournalEntry.id == entry_id))
        assert entrada is not None
        assert entrada.estado == JournalEntryEstado.POSTED
        entrada.concepto = "Cambio prohibido"
        await s.flush()

    with pytest.raises(IntegrityError):
        await journal_api.consultar(_intentar)