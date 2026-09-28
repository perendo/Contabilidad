"""T115: Aislamiento multi-tenant US3 (SPEC-006).

Empresa A crea y anula su asiento; empresa B no ve ni el original ni el
rectificativo.
"""

from __future__ import annotations

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000"},
]

BODY = {"fecha": "2026-01-15", "concepto": "Gastos varios", "lineas": LINEAS_3_2}


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_empresa_b_no_ve_original_ni_rectificativo(asientos_client):
    client, token, _ = asientos_client
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text
    original_id = creado.json()["id"]

    anul = client.post(f"/api/v1/asientos/{original_id}/anular", headers=_hh(token, 10))
    assert anul.status_code == 201, anul.text
    rect_id = anul.json()["asiento_rectificativo"]["id"]

    for detalle_id in (original_id, rect_id):
        resp = client.get(f"/api/v1/asientos/{detalle_id}", headers=_hh(token, 20))
        assert resp.status_code == 404
        resp_anular = client.post(
            f"/api/v1/asientos/{detalle_id}/anular", headers=_hh(token, 20)
        )
        assert resp_anular.status_code == 404

    listado_b = client.get("/api/v1/asientos", headers=_hh(token, 20))
    assert listado_b.json()["total"] == 0