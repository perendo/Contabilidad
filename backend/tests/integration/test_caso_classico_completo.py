"""T107: Test integración caso clásico 1:1 (SPEC-006 US2)."""

from __future__ import annotations

LINEAS_1_1 = [
    {"cuenta": "4100", "debe": "1200.0000", "haber": "0.0000", "detalle": "Proveedor"},
    {"cuenta": "5720", "debe": "0.0000", "haber": "1200.0000", "detalle": "Banco"},
]

BODY = {"fecha": "2026-01-16", "concepto": "Pago proveedor", "lineas": LINEAS_1_1}


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_caso_classico_1_1_via_http(asientos_client):
    client, token, _ = asientos_client
    resp = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert cuerpo["n_lineas"] == 2
    assert cuerpo["total_debe"] == cuerpo["total_haber"] == "1200.0000"

    listado = client.get(
        "/api/v1/asientos",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-01-31"},
        headers=_hh(token, 10),
    )
    assert listado.status_code == 200
    assert listado.json()["total"] == 1
    item = listado.json()["items"][0]
    assert item["id"] == cuerpo["id"]
    assert item["n_lineas"] == 2
    assert item["concepto"] == "Pago proveedor"


def test_cuentas_repetidas_admitidas(asientos_client):
    client, token, _ = asientos_client
    repes = {
        "fecha": "2026-01-16",
        "concepto": "Dos compras misma cuenta",
        "lineas": [
            {"cuenta": "6000", "debe": "100.0000", "haber": "0.0000"},
            {"cuenta": "6000", "debe": "50.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "150.0000"},
        ],
    }
    resp = client.post("/api/v1/asientos", json=repes, headers=_hh(token, 10))
    assert resp.status_code == 201, resp.text
    assert resp.json()["n_lineas"] == 3