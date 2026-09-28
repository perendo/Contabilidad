"""Test aislamiento multi-tenant US3 (SPEC-022 T042).

Empresa A cede cobros; desde empresa B la cesión no es visible (GET → 404)
y el listado de B no la incluye.
"""

from __future__ import annotations


def _crear_cesion(api, empresa_id):
    return api.post(
        "/api/v1/cesiones",
        empresa_id=empresa_id,
        json={
            "entidad_financiera": "Banco A",
            "fecha_cesion": "2026-10-01",
            "vencimiento_ids": [str(v) for v in api.vencimientos[empresa_id][:1]],
            "comision": "0.0000",
            "tipo_comision": "IMPORTE_FIJO",
        },
    )


def test_cesion_de_a_invisible_desde_b(anticipos_client):
    api = anticipos_client
    r = _crear_cesion(api, 10)
    assert r.status_code == 201, r.text
    cesion_id = r.json()["id"]

    assert api.get(20, f"/api/v1/cesiones/{cesion_id}").status_code == 404

    lista_b = api.get(20, "/api/v1/cesiones").json()
    assert lista_b["total"] == 0
    lista_a = api.get(10, "/api/v1/cesiones").json()
    assert lista_a["total"] == 1


def test_cesion_de_b_no_afecta_a_a(anticipos_client):
    api = anticipos_client
    r = _crear_cesion(api, 20)
    assert r.status_code == 201, r.text
    cesion_b = r.json()["id"]

    assert api.get(10, f"/api/v1/cesiones/{cesion_b}").status_code == 404
    assert api.get(10, "/api/v1/cesiones").json()["total"] == 0