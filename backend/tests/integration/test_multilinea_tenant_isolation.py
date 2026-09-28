"""T005: Aislamiento multi-tenant foundational (SPEC-006).

Crear asiento en la empresa A (10) y verificar que la empresa B (20) no lo ve
via GET ni puede anularlo (404 en ambos casos).
"""

from __future__ import annotations

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Compra"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Alquiler"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldo"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Prov A"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Prov B"},
]

BODY = {"fecha": "2026-01-15", "concepto": "Gastos varios", "lineas": LINEAS_3_2}


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_empresa_b_no_ve_ni_anula_asiento_de_a(asientos_client):
    client, token, _ = asientos_client
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text
    asiento_id = creado.json()["id"]

    detalle_b = client.get(f"/api/v1/asientos/{asiento_id}", headers=_hh(token, 20))
    assert detalle_b.status_code == 404

    anular_b = client.post(f"/api/v1/asientos/{asiento_id}/anular", headers=_hh(token, 20))
    assert anular_b.status_code == 404

    listado_b = client.get("/api/v1/asientos", headers=_hh(token, 20))
    assert listado_b.status_code == 200
    assert listado_b.json()["total"] == 0