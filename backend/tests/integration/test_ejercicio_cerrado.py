"""Integration tests SPEC-002 T041: ejercicio cerrado bloquea el motor (SC-005)."""

from __future__ import annotations

from datetime import date

from models.acct.fiscal_year import FiscalYear


def _cerrar_2026(journal_api):
    async def _add(s):
        s.add(
            FiscalYear(
                empresa_id=10,
                year=2026,
                date_start=date(2026, 1, 1),
                date_end=date(2026, 12, 31),
                is_closed=True,
            )
        )

    return journal_api.mutar(_add)


async def test_crear_en_ejercicio_cerrado_400(journal_api):
    await _cerrar_2026(journal_api)
    respuesta = journal_api.crear(fecha="2026-10-01", concepto="Cerrado")
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"]["code"] == "ejercicio_cerrado"


async def test_asentar_en_ejercicio_cerrado_400_sin_efecto(journal_api):
    borrador = journal_api.crear(fecha="2026-10-01", concepto="Antes de cerrar")
    entry_id = borrador.json()["id"]
    assert borrador.status_code == 201
    await _cerrar_2026(journal_api)

    respuesta = journal_api.asentar(entry_id)
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"]["code"] == "ejercicio_cerrado"
    # El borrador sigue DRAFT y sin numerar
    detalle = journal_api.detalle(entry_id)
    assert detalle.json()["estado"] == "DRAFT"
    assert detalle.json()["numero"] is None


async def test_anular_en_ejercicio_cerrado_400(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Posteado")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200
    await _cerrar_2026(journal_api)

    respuesta = journal_api.anular(entry_id, fecha="2026-10-05")
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"]["code"] == "ejercicio_cerrado"
    assert journal_api.detalle(entry_id).json()["estado"] == "POSTED"


async def test_ejercicio_sin_fila_tratado_como_abierto(journal_api):
    """Sin fila fiscal_year para 2027 el motor opera normal (guarda SPEC-004)."""
    creado = journal_api.crear(fecha="2027-02-01", concepto="Abierto 2027")
    assert creado.status_code == 201
    asentado = journal_api.asentar(creado.json()["id"])
    assert asentado.status_code == 200
    assert asentado.json()["numero"] == 1
    assert asentado.json()["ejercicio"] == 2027