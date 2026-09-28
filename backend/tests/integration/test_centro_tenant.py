"""T022: Aislamiento multi-tenant de centros por HTTP (SPEC-017, constitución III).

Los centros creados en A son invisibles para B en listados, árbol y detalle;
la edición/inactivación de un centro de A bajo la empresa B responde 404.
"""

from __future__ import annotations

import uuid


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_crear_en_a_no_visible_en_b(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/centros", json={"codigo": "SECR", "nombre": "Secreto", "tipo": "proyecto"}, headers=_hh(token, 10))
    assert r.status_code == 201
    centro = r.json()["id"]

    r = client.get("/api/v1/centros", headers=_hh(token, 20))
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []

    r = client.get("/api/v1/centros/arbol", headers=_hh(token, 20))
    assert r.json()["items"] == []
    assert r.json()["total"] == 0

    r = client.get(f"/api/v1/centros/{centro}", headers=_hh(token, 20))
    assert r.status_code == 404


def test_editar_y_estado_cross_tenant_404(costcenters_client):
    client, token, _ = costcenters_client
    centro = client.post("/api/v1/centros", json={"codigo": "XA", "nombre": "XA", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]

    r = client.patch(f"/api/v1/centros/{centro}", json={"nombre": "Nuevo"}, headers=_hh(token, 20))
    assert r.status_code == 404

    r = client.post(f"/api/v1/centros/{centro}/inactivar", headers=_hh(token, 20))
    assert r.status_code == 404

    r = client.post(f"/api/v1/centros/{centro}/reactivar", headers=_hh(token, 20))
    assert r.status_code == 404


def test_codigo_duplicado_solo_dentro_de_la_empresa(costcenters_client):
    client, token, _ = costcenters_client
    payload = {"codigo": "MISMO", "nombre": "Mismo código", "tipo": "proyecto"}
    assert client.post("/api/v1/centros", json=payload, headers=_hh(token, 10)).status_code == 201
    r = client.post("/api/v1/centros", json=payload, headers=_hh(token, 20))
    assert r.status_code == 201


def test_arbol_escopeta_por_empresa(costcenters_client):
    """Sendas distintas en A y B: A ve solo su rama, B solo la suya."""
    client, token, _ = costcenters_client
    raiz_a = client.post("/api/v1/centros", json={"codigo": "RA", "nombre": "Rama A", "tipo": "departamento"}, headers=_hh(token, 10)).json()["id"]
    hijo_a = client.post("/api/v1/centros", json={"codigo": "HA", "nombre": "Hijo A", "tipo": "proyecto", "parent_id": raiz_a}, headers=_hh(token, 10)).json()["id"]

    raiz_b = client.post("/api/v1/centros", json={"codigo": "RB", "nombre": "Rama B", "tipo": "departamento"}, headers=_hh(token, 20)).json()["id"]
    client.post("/api/v1/centros", json={"codigo": "HB", "nombre": "Hijo B", "tipo": "proyecto", "parent_id": raiz_b}, headers=_hh(token, 20))

    arbol_a = client.get("/api/v1/centros/arbol", headers=_hh(token, 10)).json()
    assert arbol_a["total"] == 2
    assert arbol_a["items"][0]["hijos"][0]["id"] == hijo_a

    arbol_b = client.get("/api/v1/centros/arbol", headers=_hh(token, 20)).json()
    assert arbol_b["total"] == 2
    assert arbol_b["items"][0]["codigo"] == "RB"


def test_uuid_ajeno_no_filtra_otra_empresa(costcenters_client):
    client, token, _ = costcenters_client
    r = client.get(f"/api/v1/centros/{uuid.uuid4()}", headers=_hh(token, 10))
    assert r.status_code == 404