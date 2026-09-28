"""T033: Aislamiento de imputaciones entre empresas por HTTP (SPEC-017 III).

Las imputaciones de A no son visibles desde B, ni los asientos imputados; la
rectificación de una línea de A bajo empresa B responde 404.
"""

from __future__ import annotations

import uuid


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _asiento(centro_id) -> dict:
    return {
        "fecha": "2026-05-14",
        "concepto": "Gasto",
        "lineas": [
            {"cuenta": "4300", "debe": "88.0000", "haber": "0", "centro_coste_id": str(centro_id)},
            {"cuenta": "5720", "debe": "0", "haber": "88.0000"},
        ],
    }


def test_imputaciones_de_a_invisibles_desde_b(costcenters_client):
    client, token, _ = costcenters_client
    centro = client.post("/api/v1/centros", json={"codigo": "ISO", "nombre": "Aislado", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    asiento = client.post("/api/v1/asientos", json=_asiento(centro), headers=_hh(token, 10)).json()["id"]

    r = client.get("/api/v1/imputaciones", params={"asiento_id": asiento}, headers=_hh(token, 20))
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0

    r = client.get("/api/v1/imputaciones", headers=_hh(token, 20))
    assert r.json()["total"] == 0


def test_asiento_imputado_de_a_no_se_ve_desde_b(costcenters_client):
    client, token, _ = costcenters_client
    centro = client.post("/api/v1/centros", json={"codigo": "OCU", "nombre": "Oculto", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    asiento = client.post("/api/v1/asientos", json=_asiento(centro), headers=_hh(token, 10)).json()["id"]

    r = client.get(f"/api/v1/asientos/{asiento}", headers=_hh(token, 20))
    assert r.status_code == 404

    r = client.get("/api/v1/asientos", headers=_hh(token, 20))
    assert r.json()["total"] == 0


def test_rectificacion_cross_tenant_404(costcenters_client):
    client, token, _ = costcenters_client
    centro_a = client.post("/api/v1/centros", json={"codigo": "RA", "nombre": "RA", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    asiento = client.post("/api/v1/asientos", json=_asiento(centro_a), headers=_hh(token, 10)).json()["id"]
    detalle = client.get(f"/api/v1/asientos/{asiento}", headers=_hh(token, 10)).json()
    linea = detalle["lineas"][0]

    centro_b = client.post("/api/v1/centros", json={"codigo": "RB", "nombre": "RB", "tipo": "proyecto"}, headers=_hh(token, 20)).json()["id"]
    r = client.post(
        f"/api/v1/asientos/{asiento}/lineas/{linea['id']}/rectificar-imputacion",
        json={"centro_coste_id": centro_b},
        headers=_hh(token, 20),
    )
    assert r.status_code == 404


def test_asiento_con_centro_inexistente_404_desde_la_otra_empresa(costcenters_client):
    client, token, _ = costcenters_client
    centro_a = client.post("/api/v1/centros", json={"codigo": "AZ", "nombre": "AZ", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]

    # B intenta crear un asiento imputado al centro de A -> 404
    r = client.post("/api/v1/asientos", json=_asiento(centro_a), headers=_hh(token, 20))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "centro_no_encontrado"


def test_imputar_linea_cross_tenant_404(costcenters_client):
    client, token, _ = costcenters_client
    centro_a = client.post("/api/v1/centros", json={"codigo": "LA", "nombre": "LA", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    asiento = client.post("/api/v1/asientos", json=_asiento(centro_a), headers=_hh(token, 10)).json()["id"]
    detalle = client.get(f"/api/v1/asientos/{asiento}", headers=_hh(token, 10)).json()
    linea = detalle["lineas"][0]

    r = client.post(
        f"/api/v1/asientos/{asiento}/lineas/{linea['id']}/imputar",
        json={"centro_coste_id": str(uuid.uuid4())},
        headers=_hh(token, 20),
    )
    assert r.status_code == 404