"""Test aislamiento multi-tenant US2 (SPEC-022 T030).

Empresa A crea un anticipo de proveedor; desde empresa B no es visible
(GET → 404) y el listado de B no lo incluye.
"""

from __future__ import annotations


def test_anticipo_proveedor_de_a_invisible_desde_b(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        empresa_id=10,
        json={
            "tercero_id": str(api.proveedores[10]),
            "tipo": "PROVEEDOR",
            "fecha": "2026-03-01",
            "importe": "1200.0000",
            "concepto": "Anticipo proveedor A",
        },
    )
    assert r.status_code == 201, r.text
    anticipo_id = r.json()["id"]

    assert api.get(20, f"/api/v1/anticipos/{anticipo_id}").status_code == 404

    lista_b = api.get(20, "/api/v1/anticipos").json()
    assert lista_b["total"] == 0

    r = api.post(
        "/api/v1/anticipos",
        empresa_id=20,
        json={
            "tercero_id": str(api.proveedores[20]),
            "tipo": "PROVEEDOR",
            "fecha": "2026-03-02",
            "importe": "800.0000",
            "concepto": "Anticipo proveedor B",
        },
    )
    assert r.status_code == 201, r.text
    assert api.get(10, f"/api/v1/anticipos/{r.json()['id']}").status_code == 404