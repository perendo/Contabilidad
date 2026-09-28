"""Test aislamiento multi-tenant US1 (SPEC-022 T023).

Empresa A crea un anticipo y lo liquida; desde empresa B no es visible
(GET → 404) ni se puede liquidar (POST liquidar → 404).
"""

from __future__ import annotations


def _crear(api, empresa_id):
    return api.post(
        "/api/v1/anticipos",
        empresa_id=empresa_id,
        json={
            "tercero_id": str(api.terceros[empresa_id]),
            "tipo": "CLIENTE",
            "fecha": "2026-03-01",
            "importe": "1000.0000",
            "concepto": "Anticipo A",
        },
    )


def test_anticipo_de_a_invisible_y_no_liquidable_desde_b(anticipos_client):
    api = anticipos_client
    r = _crear(api, 10)
    assert r.status_code == 201, r.text
    anticipo_id = r.json()["id"]

    assert api.get(20, f"/api/v1/anticipos/{anticipo_id}").status_code == 404
    r = api.post(
        f"/api/v1/anticipos/{anticipo_id}/liquidar",
        empresa_id=20,
        json={
            "aplicaciones": [
                {"factura_id": str(api.facturas[20]["venta"]), "importe_aplicado": "500.0000"}
            ],
            "fecha_aplicacion": "2026-06-01",
        },
    )
    assert r.status_code == 404

    lista = api.get(20, "/api/v1/anticipos").json()
    assert lista["total"] == 0
    lista_a = api.get(10, "/api/v1/anticipos").json()
    assert lista_a["total"] == 1


def test_crear_anticipo_en_b_es_independiente(anticipos_client):
    api = anticipos_client
    r = _crear(api, 20)
    assert r.status_code == 201, r.text
    lista_a = api.get(10, "/api/v1/anticipos").json()
    assert lista_a["total"] == 0
    lista_b = api.get(20, "/api/v1/anticipos").json()
    assert lista_b["total"] == 1