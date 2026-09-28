"""T126: Escenarios del quickstart de SPEC-006 reproducidos por HTTP.

Los 6 escenarios de `specs/006-asientos-multilinea/quickstart.md` (adaptados
a los códigos del PGC sembrado: 6000/6210/6400/4000/4100/5720).
"""

from __future__ import annotations


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_escenario_1_crear_3_2_balanceado(asientos_client):
    client, token, _ = asientos_client
    resp = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-01-15",
            "concepto": "Gasto compuesto parcialmente deducible",
            "lineas": [
                {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Material"},
                {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Servicios"},
                {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldos"},
                {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Prov A"},
                {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Prov B"},
            ],
        },
        headers=_hh(token, 10),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["total_debe"] == "500.0000"
    assert resp.json()["total_haber"] == "500.0000"
    assert resp.json()["n_lineas"] == 5
    assert resp.json()["estado"] == "POSTED"


def test_escenario_2_rechazo_lado_vacio(asientos_client):
    client, token, _ = asientos_client
    resp = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-01-15",
            "concepto": "Asiento incompleto",
            "lineas": [
                {"cuenta": "6000", "debe": "500.0000", "haber": "0.0000"},
                {"cuenta": "6210", "debe": "200.0000", "haber": "0.0000"},
            ],
        },
        headers=_hh(token, 10),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "lado_vacio"
    assert "HABER" in resp.json()["detail"]["detail"]


def test_escenario_3_rechazo_desbalanceo(asientos_client):
    client, token, _ = asientos_client
    resp = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-01-15",
            "concepto": "Desbalanceado",
            "lineas": [
                {"cuenta": "6000", "debe": "500.0000", "haber": "0.0000"},
                {"cuenta": "4000", "debe": "0.0000", "haber": "450.0000"},
            ],
        },
        headers=_hh(token, 10),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "desbalanceo"


def test_escenario_4_anulacion(asientos_client):
    client, token, _ = asientos_client
    creado = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-01-15",
            "concepto": "Gastos varios",
            "lineas": [
                {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000"},
                {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000"},
                {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000"},
                {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000"},
                {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000"},
            ],
        },
        headers=_hh(token, 10),
    )
    asiento_id = creado.json()["id"]

    anul = client.post(f"/api/v1/asientos/{asiento_id}/anular", headers=_hh(token, 10))
    assert anul.status_code == 201, anul.text
    rect = anul.json()["asiento_rectificativo"]
    assert rect["tipo"] == "REVERSAL"
    assert rect["n_lineas"] == 5
    assert rect["total_debe"] == rect["total_haber"] == "500.0000"
    assert anul.json()["asiento_original_id"] == asiento_id

    original = client.get(f"/api/v1/asientos/{asiento_id}", headers=_hh(token, 10))
    assert original.json()["estado"] == "CANCELLED"
    assert original.json()["tipo"] == "GENERAL"
    detalle_rect = client.get(f"/api/v1/asientos/{rect['id']}", headers=_hh(token, 10))
    assert detalle_rect.json()["estado"] == "POSTED"


def test_escenario_5_caso_classico_1_1(asientos_client):
    client, token, _ = asientos_client
    resp = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-01-16",
            "concepto": "Pago proveedor",
            "lineas": [
                {"cuenta": "4100", "debe": "1200.0000", "haber": "0.0000"},
                {"cuenta": "5720", "debe": "0.0000", "haber": "1200.0000"},
            ],
        },
        headers=_hh(token, 10),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["n_lineas"] == 2
    assert resp.json()["total_debe"] == resp.json()["total_haber"] == "1200.0000"


def test_escenario_6_aislamiento(asientos_client):
    client, token, _ = asientos_client
    creado = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-01-15",
            "concepto": "Gastos varios",
            "lineas": [
                {"cuenta": "6000", "debe": "100.0000", "haber": "0.0000"},
                {"cuenta": "4000", "debe": "0.0000", "haber": "100.0000"},
            ],
        },
        headers=_hh(token, 10),
    )
    asiento_id = creado.json()["id"]
    assert client.get(f"/api/v1/asientos/{asiento_id}", headers=_hh(token, 20)).status_code == 404
    assert client.post(
        f"/api/v1/asientos/{asiento_id}/anular", headers=_hh(token, 20)
    ).status_code == 404