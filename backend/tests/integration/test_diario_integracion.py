"""Integration tests SPEC-002 T028: libro diario end-to-end (US2)."""

from __future__ import annotations


async def test_orden_por_fecha_y_numero(journal_api):
    """(fecha, numero): primero el asiento antiguo, luego 10-01 en orden."""
    for i in range(2):
        creado = journal_api.crear(fecha="2026-10-01", concepto=f"Octubre {i+1}")
        assert journal_api.asentar(creado.json()["id"]).status_code == 200
    antes = journal_api.crear(fecha="2026-09-29", concepto="Septiembre")
    assert journal_api.asentar(antes.json()["id"]).status_code == 200

    diario = journal_api.diario(
        date_from="2026-09-01", date_to="2026-10-31"
    )
    items = diario.json()["items"]
    assert [item["concepto"] for item in items] == [
        "Septiembre",
        "Octubre 1",
        "Octubre 2",
    ]
    assert [item["fecha"] for item in items] == [
        "2026-09-29",
        "2026-10-01",
        "2026-10-01",
    ]
    # Orden por (fecha, numero): [09-29 n3, 10-01 n1, 10-01 n2]
    assert [item["numero"] for item in items] == [3, 1, 2]
    for item in items:
        assert item["suma_debe"] == item["suma_haber"] == "100.0000"
        assert item["lineas"] == 2


async def test_detalle_con_cuentas_y_detalle(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Venta detalle")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200

    detalle = journal_api.detalle(entry_id)
    assert detalle.status_code == 200
    body = detalle.json()
    assert body["estado"] == "POSTED"
    assert body["numero"] == 1
    assert body["lineas"][0]["account_code"] == "4300"
    assert body["lineas"][0]["account_name"] == "Clientes detalle"
    assert body["lineas"][0]["debit"] == "100.0000"
    assert body["lineas"][0]["credit"] == "0.0000"
    assert body["lineas"][1]["account_code"] == "5720"
    assert body["lineas"][1]["credit"] == "100.0000"


async def test_borrador_visible_por_id_pero_no_en_diario(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Borrador")
    entry_id = creado.json()["id"]
    assert journal_api.detalle(entry_id).status_code == 200
    diario = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-31"
    )
    assert diario.json()["total"] == 0


async def test_detalle_inexistente_404(journal_api):
    import uuid

    assert journal_api.detalle(uuid.uuid4()).status_code == 404


# ---------------------------------------------------------------------------
# Filtro de estado (apertura del libro a los borradores bajo demanda)
# ---------------------------------------------------------------------------


async def test_estado_draft_devuelve_borradores(journal_api):
    """Pedir DRAFT a mano es la única vía para ver un borrador en el diario."""
    borrador = journal_api.crear(fecha="2026-10-01", concepto="Sin asentar")
    assert borrador.json()["estado"] == "DRAFT"

    diario = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-31", estado="DRAFT"
    )
    assert diario.status_code == 200
    assert diario.json()["total"] == 1
    assert diario.json()["items"][0]["concepto"] == "Sin asentar"
    assert diario.json()["items"][0]["estado"] == "DRAFT"


async def test_sin_filtro_sigue_excluyendo_borradores(journal_api):
    """El contrato por defecto no cambia: la apertura es opt-in, no la nueva norma.

    Es la mitad que protege `test_borrador_visible_por_id_pero_no_en_diario` ante el
    filtro nuevo: un `estado=None` mal propagado devolvería los borradores y no lo
    diría ningún test que solo mira el filtro explícito.
    """
    journal_api.crear(fecha="2026-10-01", concepto="Sin asentar")
    asentado = journal_api.crear(fecha="2026-10-02", concepto="Asentado")
    assert journal_api.asentar(asentado.json()["id"]).status_code == 200

    por_defecto = journal_api.diario(date_from="2026-10-01", date_to="2026-10-31")
    assert por_defecto.status_code == 200
    assert [i["concepto"] for i in por_defecto.json()["items"]] == ["Asentado"]

    todos = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-31", estado="DRAFT,POSTED,CANCELLED"
    )
    assert sorted(i["concepto"] for i in todos.json()["items"]) == [
        "Asentado",
        "Sin asentar",
    ]


async def test_estado_admite_minusculas_y_espacios(journal_api):
    journal_api.crear(fecha="2026-10-01", concepto="Borrador")
    diario = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-31", estado=" draft , posted "
    )
    assert diario.status_code == 200
    assert diario.json()["total"] == 1


async def test_estado_desconocido_422(journal_api):
    """Un estado mal escrito no puede devolver cero filas en silencio.

    Sería indistinguible de "no hay nada", que es exactamente el síntoma que
    estamos arreglando. Por eso el código es `estado_desconocido` y no
    `estado_invalido`: este último lo usa `_http_error` para un 409 de transición.
    """
    diario = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-31", estado="BORRADOR"
    )
    assert diario.status_code == 422
    assert diario.json()["detail"]["code"] == "estado_desconocido"


async def test_estado_vacio_422(journal_api):
    diario = journal_api.diario(
        date_from="2026-10-01", date_to="2026-10-31", estado="  ,  "
    )
    assert diario.status_code == 422
    assert diario.json()["detail"]["code"] == "estado_vacio"


async def test_filtro_estado_respeta_la_empresa_activa(journal_api):
    """El filtro abre el libro, no el aislamiento (constitución III)."""
    a = journal_api.crear(empresa_id=10, fecha="2026-10-01", concepto="De A")
    b = journal_api.crear(empresa_id=20, fecha="2026-10-01", concepto="De B")
    assert a.status_code == 201 and b.status_code == 201

    desde_a = journal_api.diario(
        empresa_id=10,
        date_from="2026-10-01",
        date_to="2026-10-31",
        estado="DRAFT",
    )
    assert [i["concepto"] for i in desde_a.json()["items"]] == ["De A"]