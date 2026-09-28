"""Hardening multi-tenant completo (SPEC-022 T044).

Escenario cross-empresa: anticipo y cesión de A; empresa B no ve nada y no
puede liquidar el anticipo de A (404). También vencimientos cedidos de A
no son cedibles desde B ni visibles en su listado.
"""

from __future__ import annotations


def test_flujo_cross_empresa_aislado(anticipos_client):
    api = anticipos_client

    r = api.post(
        "/api/v1/anticipos",
        empresa_id=10,
        json={
            "tercero_id": str(api.terceros[10]),
            "tipo": "CLIENTE",
            "fecha": "2026-03-01",
            "importe": "1000.0000",
            "concepto": "Anticipo A",
        },
    )
    assert r.status_code == 201, r.text
    anticipo_a = r.json()["id"]

    r = api.post(
        "/api/v1/cesiones",
        empresa_id=10,
        json={
            "entidad_financiera": "Banco A",
            "fecha_cesion": "2026-10-01",
            "vencimiento_ids": [str(v) for v in api.vencimientos[10][:1]],
            "comision": "0.0000",
            "tipo_comision": "IMPORTE_FIJO",
        },
    )
    assert r.status_code == 201, r.text
    cesion_a = r.json()["id"]

    assert api.get(20, f"/api/v1/anticipos/{anticipo_a}").status_code == 404
    assert api.get(20, f"/api/v1/cesiones/{cesion_a}").status_code == 404

    r = api.post(
        f"/api/v1/anticipos/{anticipo_a}/liquidar",
        empresa_id=20,
        json={
            "aplicaciones": [
                {"factura_id": str(api.facturas[20]["venta"]), "importe_aplicado": "500.0000"}
            ],
            "fecha_aplicacion": "2026-06-01",
        },
    )
    assert r.status_code == 404

    r = api.post(
        "/api/v1/cesiones",
        empresa_id=20,
        json={
            "entidad_financiera": "Banco B",
            "fecha_cesion": "2026-10-01",
            "vencimiento_ids": [str(api.vencimientos[10][0])],
            "comision": "0.0000",
            "tipo_comision": "IMPORTE_FIJO",
        },
    )
    assert r.status_code == 422  # vencimiento inexistente para la empresa activa

    assert api.get(20, "/api/v1/anticipos").json()["total"] == 0
    assert api.get(20, "/api/v1/cesiones").json()["total"] == 0
    assert api.get(10, "/api/v1/anticipos").json()["total"] == 1
    assert api.get(10, "/api/v1/cesiones").json()["total"] == 1