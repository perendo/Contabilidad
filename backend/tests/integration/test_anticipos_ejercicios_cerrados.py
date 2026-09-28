"""Validación de ejercicios cerrados (SPEC-022 T047).

Anticipos, liquidaciones y cesiones rechazan con 409 ``ejercicio_cerrado``
cuando su fecha cae en un ejercicio cerrado (SPEC-002/004). El fixture
``anticipos_client`` siembra un ``FiscalYear`` 2025 cerrado.
"""

from __future__ import annotations


def test_anticipo_en_ejercicio_cerrado_409(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        json={
            "tercero_id": str(api.terceros[10]),
            "tipo": "CLIENTE",
            "fecha": "2025-06-01",
            "importe": "1000.0000",
            "concepto": "Anticipo 2025",
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_anticipo_abierto_en_ejercicio_abierto_201(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        json={
            "tercero_id": str(api.terceros[10]),
            "tipo": "CLIENTE",
            "fecha": "2026-06-01",
            "importe": "1000.0000",
            "concepto": "Anticipo 2026",
        },
    )
    assert r.status_code == 201, r.text


def test_liquidacion_en_ejercicio_cerrado_409(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        json={
            "tercero_id": str(api.terceros[10]),
            "tipo": "CLIENTE",
            "fecha": "2026-06-01",
            "importe": "1000.0000",
            "concepto": "Anticipo 2026",
        },
    )
    anticipo_id = r.json()["id"]
    r = api.post(
        f"/api/v1/anticipos/{anticipo_id}/liquidar",
        json={
            "aplicaciones": [
                {"factura_id": str(api.facturas[10]["venta"]), "importe_aplicado": "500.0000"}
            ],
            "fecha_aplicacion": "2025-12-31",
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_cesion_en_ejercicio_cerrado_409(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/cesiones",
        json={
            "entidad_financiera": "Banco",
            "fecha_cesion": "2025-10-01",
            "vencimiento_ids": [str(v) for v in api.vencimientos[10][:1]],
            "comision": "0.0000",
            "tipo_comision": "IMPORTE_FIJO",
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"