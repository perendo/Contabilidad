"""T108: Aislamiento multi-tenant US2 (SPEC-006).

Empresa A crea un 1:1; empresa B no lo ve.
"""

from __future__ import annotations

BODY = {
    "fecha": "2026-01-16",
    "concepto": "Pago proveedor",
    "lineas": [
        {"cuenta": "4100", "debe": "1200.0000", "haber": "0.0000"},
        {"cuenta": "5720", "debe": "0.0000", "haber": "1200.0000"},
    ],
}


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_empresa_b_no_ve_el_1_1_de_a(asientos_client):
    client, token, _ = asientos_client
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text

    oculto = client.get(
        f"/api/v1/asientos/{creado.json()['id']}", headers=_hh(token, 20)
    )
    assert oculto.status_code == 404

    listado_b = client.get("/api/v1/asientos", headers=_hh(token, 20))
    assert listado_b.json()["total"] == 0