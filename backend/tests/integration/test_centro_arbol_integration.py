"""T021: Árbol de centros vía HTTP (SPEC-017 US1, integración).

Los endpoints `/api/v1/centros` crean, listan y devuelven el árbol completo
resuelto con `profundidad`, manteniendo tres niveles padre→hijo→nieto.
"""

from __future__ import annotations

import uuid


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_flujo_arbol_completo(costcenters_client):
    client, token, _ = costcenters_client

    r = client.post("/api/v1/centros", json={"codigo": "DIR", "nombre": "Dirección", "tipo": "departamento"}, headers=_hh(token, 10))
    assert r.status_code == 201
    dir_id = r.json()["id"]
    assert r.json()["es_hoja"] is True

    r = client.post("/api/v1/centros", json={"codigo": "PYX", "nombre": "Proyecto X", "tipo": "proyecto", "parent_id": dir_id}, headers=_hh(token, 10))
    assert r.status_code == 201
    pyx_id = r.json()["id"]
    assert r.json()["parent_id"] == dir_id

    r = client.post("/api/v1/centros", json={"codigo": "SUB", "nombre": "Subvención", "tipo": "subvencion", "parent_id": pyx_id}, headers=_hh(token, 10))
    assert r.status_code == 201
    sub_id = r.json()["id"]

    r = client.get("/api/v1/centros/arbol", headers=_hh(token, 10))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    raiz = body["items"][0]
    assert raiz["id"] == dir_id
    assert raiz["profundidad"] == 0
    hijo = raiz["hijos"][0]
    assert hijo["id"] == pyx_id
    assert hijo["profundidad"] == 1
    nieto = hijo["hijos"][0]
    assert nieto["id"] == sub_id
    assert nieto["profundidad"] == 2

    r = client.get("/api/v1/centros", headers=_hh(token, 10))
    assert r.status_code == 200
    assert r.json()["total"] == 3

    r = client.get(f"/api/v1/centros/{dir_id}", headers=_hh(token, 10))
    assert r.status_code == 200
    assert r.json()["hijos"][0]["id"] == pyx_id


def test_inactivar_y_reactivar(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/centros", json={"codigo": "TOG", "nombre": "Toggle", "tipo": "proyecto"}, headers=_hh(token, 10))
    centro = r.json()["id"]

    r = client.post(f"/api/v1/centros/{centro}/inactivar", headers=_hh(token, 10))
    assert r.status_code == 200
    assert r.json()["estado"] == "inactivo"

    r = client.post(f"/api/v1/centros/{centro}/reactivar", headers=_hh(token, 10))
    assert r.status_code == 200
    assert r.json()["estado"] == "activo"


def test_reparenting_preserva_closure(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/centros", json={"codigo": "P1", "nombre": "P1", "tipo": "departamento"}, headers=_hh(token, 10))
    p1 = r.json()["id"]
    r = client.post("/api/v1/centros", json={"codigo": "P2", "nombre": "P2", "tipo": "departamento"}, headers=_hh(token, 10))
    p2 = r.json()["id"]
    r = client.post("/api/v1/centros", json={"codigo": "H1", "nombre": "H1", "tipo": "proyecto", "parent_id": p1}, headers=_hh(token, 10))
    h1 = r.json()["id"]

    r = client.patch(f"/api/v1/centros/{h1}", json={"parent_id": p2}, headers=_hh(token, 10))
    assert r.status_code == 200

    r = client.get("/api/v1/centros/arbol", headers=_hh(token, 10))
    items = {c["id"]: c for c in _aplanar(r.json()["items"])}
    assert items[p1]["n_hijos"] == 0
    assert items[p2]["n_hijos"] == 1
    assert items[p2]["hijos"][0]["id"] == h1


def _aplanar(nodos):
    for n in nodos:
        yield n
        yield from _aplanar(n.get("hijos", []))


def test_ciclo_en_edicion_409(costcenters_client):
    client, token, _ = costcenters_client
    padre = client.post("/api/v1/centros", json={"codigo": "PC", "nombre": "Padre", "tipo": "departamento"}, headers=_hh(token, 10)).json()["id"]
    hijo = client.post("/api/v1/centros", json={"codigo": "HC", "nombre": "Hijo", "tipo": "proyecto", "parent_id": padre}, headers=_hh(token, 10)).json()["id"]

    r = client.patch(f"/api/v1/centros/{padre}", json={"parent_id": hijo}, headers=_hh(token, 10))
    assert r.status_code == 409


def test_codigo_duplicado_409(costcenters_client):
    client, token, _ = costcenters_client
    payload = {"codigo": "DUP", "nombre": "Duplicado", "tipo": "proyecto"}
    assert client.post("/api/v1/centros", json=payload, headers=_hh(token, 10)).status_code == 201
    r = client.post("/api/v1/centros", json=payload, headers=_hh(token, 10))
    assert r.status_code == 409


def test_detalle_404_uuid_aleatorio(costcenters_client):
    client, token, _ = costcenters_client
    r = client.get(f"/api/v1/centros/{uuid.uuid4()}", headers=_hh(token, 10))
    assert r.status_code == 404