"""Integration tests SPEC-002 T023: libro diario paginado (US2/SC-003)."""

from __future__ import annotations


def _preparar_45(journal_api):
    ids = []
    for i in range(45):
        creado = journal_api.crear(
            fecha="2026-10-01", concepto=f"Caja Día {i+1}"
        )
        assert creado.status_code == 201
        entry_id = creado.json()["id"]
        assert journal_api.asentar(entry_id).status_code == 200
        ids.append(entry_id)
    # Fuera de rango y borrador no deben aparecer en el diario de octubre
    antes = journal_api.crear(fecha="2026-09-30", concepto="Anterior")
    assert journal_api.asentar(antes.json()["id"]).status_code == 200
    despues = journal_api.crear(fecha="2026-11-30", concepto="Posterior")
    assert journal_api.asentar(despues.json()["id"]).status_code == 200
    borrador = journal_api.crear(fecha="2026-10-01", concepto="Borrador")
    assert borrador.status_code == 201
    return ids


def _numeros(respuesta):
    return [item["numero"] for item in respuesta.json()["items"]]


async def test_tres_paginas_sin_saltos(journal_api):
    _preparar_45(journal_api)
    pagina_1 = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-01", page=1, page_size=20
    )
    assert pagina_1.status_code == 200
    assert pagina_1.json()["total"] == 45
    assert pagina_1.json()["page_size"] == 20
    assert _numeros(pagina_1) == list(range(1, 21))

    pagina_2 = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-01", page=2, page_size=20
    )
    assert _numeros(pagina_2) == list(range(21, 41))

    pagina_3 = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-01", page=3, page_size=20
    )
    assert _numeros(pagina_3) == list(range(41, 46))
    assert pagina_3.json()["total"] == 45


async def test_una_sola_pagina_con_todo(journal_api):
    _preparar_45(journal_api)
    respuesta = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-01", page=1, page_size=50
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 45
    assert len(respuesta.json()["items"]) == 45
    assert respuesta.json()["page_size"] == 50


async def test_rango_obligatorio_y_orden_fechas(journal_api):
    _preparar_45(journal_api)
    # Sin rango → 422
    sin_rango = journal_api.diario()
    assert sin_rango.status_code == 422
    assert sin_rango.json()["detail"]["code"] == "rango_requerido"
    # Rango invertido → 422
    invertido = journal_api.diario(
        date_from="2026-10-31", date_to="2026-10-01"
    )
    assert invertido.status_code == 422
    assert invertido.json()["detail"]["code"] == "rango_invertido"


async def test_page_size_fuera_de_limites(journal_api):
    _preparar_45(journal_api)
    assert (
        journal_api.diario(
            date_from="2026-10-01", date_to="2026-10-01", page_size=0
        ).status_code
        == 422
    )
    assert (
        journal_api.diario(
            date_from="2026-10-01", date_to="2026-10-01", page_size=101
        ).status_code
        == 422
    )


async def test_fuera_de_rango_y_borrador_excluidos(journal_api):
    _preparar_45(journal_api)
    amplio = journal_api.diario(
        date_from="2026-01-01", date_to="2026-12-31"
    )
    assert amplio.status_code == 200
    # 45 de octubre + anterior + posterior; el borrador no cuenta
    assert amplio.json()["total"] == 47