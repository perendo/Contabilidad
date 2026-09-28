"""Tests de integracion US3 de exportacion y modelos 347/349 (SPEC-012)."""

from __future__ import annotations

EXPORT_URL = "/api/v1/fiscal/exportaciones"


def test_exportar_303_y_descargar(fiscal_client) -> None:
    fac = fiscal_client
    r = fac.post(
        EXPORT_URL,
        json={"modelo": "303", "ejercicio": 2026, "periodo": 1, "formato": "csv"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["numero_exportacion"] == 1
    assert len(data["sha256"]) == 64
    assert data["advertencia"] is None

    descarga = fac.get(10, f"{EXPORT_URL}/{data['exportacion_id']}/descargar")
    assert descarga.status_code == 200
    assert "B00000010" in descarga.text
    assert "2100.00" in descarga.text


def test_reexportar_marca_regenerado(fiscal_client) -> None:
    fac = fiscal_client
    body = {"modelo": "303", "ejercicio": 2026, "periodo": 1, "formato": "csv"}
    assert fac.post(EXPORT_URL, json=body).status_code == 201
    segunda = fac.post(EXPORT_URL, json=body)
    assert segunda.json()["numero_exportacion"] == 2
    assert segunda.json()["advertencia"] == "re-exportado"

    listado = fac.get(10, EXPORT_URL, modelo="303", ejercicio=2026).json()
    assert listado["total"] == 2


def test_347_limite_legal(fiscal_client) -> None:
    fac = fiscal_client
    data = fac.get(10, "/api/v1/modelos/347", ejercicio=2026).json()
    nifs = {op["nif_tercero"] for op in data["operaciones"]}
    assert any(op["importe_acumulado"] == "10000.0000" for op in data["operaciones"])
    assert {"B00000010", "A00000010"} <= nifs

    alto = fac.get(
        10, "/api/v1/modelos/347", ejercicio=2026, limite_incluir="20000"
    ).json()
    assert alto["operaciones"] == []
    assert alto["total_general"] == "0.0000"


def test_exportar_349_xml(fiscal_client) -> None:
    fac = fiscal_client
    fac.facturar(tipo="VENTA", base="4000.0000", tercero_key="intra", iva="0")
    r = fac.post(
        EXPORT_URL,
        json={"modelo": "349", "ejercicio": 2026, "periodo": 1, "formato": "xml"},
    )
    assert r.status_code == 201, r.text
    descarga = fac.get(10, f"{EXPORT_URL}/{r.json()['exportacion_id']}/descargar")
    assert descarga.status_code == 200
    assert "<Modelo349>" in descarga.text
    assert "DE123456789" in descarga.text


def test_descarga_multi_tenant_404(fiscal_client) -> None:
    fac = fiscal_client
    r = fac.post(EXPORT_URL, json={"modelo": "303", "ejercicio": 2026, "periodo": 1})
    export_id = r.json()["exportacion_id"]
    assert fac.get(20, f"{EXPORT_URL}/{export_id}/descargar").status_code == 404