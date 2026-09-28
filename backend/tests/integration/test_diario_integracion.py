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