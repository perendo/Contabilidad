"""T102: Aislamiento multi-tenant US1 (SPEC-006).

Empresa A crea un asiento 3:2; empresa B no lo ve en GET /asientos/{id}.
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


def test_empresa_b_no_ve_el_asiento_de_a(asientos_client):
    client, token, _ = asientos_client
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text

    oculto = client.get(
        f"/api/v1/asientos/{creado.json()['id']}", headers=_hh(token, 20)
    )
    assert oculto.status_code == 404

    visible = client.get(
        f"/api/v1/asientos/{creado.json()['id']}", headers=_hh(token, 10)
    )
    assert visible.status_code == 200