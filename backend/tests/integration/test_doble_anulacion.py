"""Integration tests SPEC-002 T031: doble anulación y estados inválidos (US3)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryTipo


def _asentado(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Una vez")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200
    return entry_id


async def test_doble_anulacion_409_sin_efectos(journal_api):
    entry_id = _asentado(journal_api)
    assert journal_api.anular(entry_id).status_code == 201

    segunda = journal_api.anular(entry_id)
    assert segunda.status_code == 409
    assert segunda.json()["detail"]["code"] == "estado_invalido"

    async def _conteo(s):
        return await s.scalar(
            select(func.count()).select_from(JournalEntry).where(
                JournalEntry.empresa_id == 10,
                JournalEntry.tipo == JournalEntryTipo.REVERSAL,
            )
        )

    # No se genera un segundo rectificativo
    assert await journal_api.consultar(_conteo) == 1


async def test_anular_borrador_409(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Borrador")
    entry_id = creado.json()["id"]
    respuesta = journal_api.anular(entry_id)
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "estado_invalido"
    # Sigue DRAFT y sin numerar
    assert journal_api.detalle(entry_id).json()["estado"] == "DRAFT"


async def test_anular_inexistente_404(journal_api):
    respuesta = journal_api.anular(uuid.uuid4())
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "asiento_no_encontrado"


async def test_anular_con_fecha_en_otro_ejercicio(journal_api):
    """La anulación se registra en el ejercicio de la fecha dada (2027)."""
    entry_id = _asentado(journal_api)
    respuesta = journal_api.anular(entry_id, fecha="2027-01-10")
    assert respuesta.status_code == 201
    assert respuesta.json()["numero_reversal"] == 1  # secuencia 2027 reinicia