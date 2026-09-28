"""SPEC-015 US1 (T021): flujo completo de la matriz.

Conceder -> el rol ejecuta; sin fila -> 403; revocar -> 403 inmediato;
reset -> seed; la concesion queda auditada.
"""

from __future__ import annotations


def _buscar(nodos, code):
    pila = list(nodos)
    while pila:
        nodo = pila.pop()
        if nodo["code"] == code:
            return nodo["id"]
        pila.extend(nodo.get("children", []))
    raise AssertionError(f"cuenta {code} no encontrada")


def _padre(rbac):
    resp = rbac.get(10, "/api/v1/accounts/tree", "admin")
    return _buscar(resp.json()["nodos"], "430")


def test_flujo_completo_conceder_ejecutar_revocar(rbac_client) -> None:
    rbac = rbac_client
    body = {"code": "4309", "name": "Concedido", "parent_id": _padre(rbac)}

    # sin fila -> denegado
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 403

    # conceder acct/crear a READ_ONLY
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 201

    # revocar -> 403 inmediato
    matriz_id = rbac.matriz_id(10, "READ_ONLY", "acct", "crear")
    assert matriz_id is not None
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_id}", 10, "admin").status_code == 204
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 403


def test_reset_reinstaura_el_seed(rbac_client) -> None:
    rbac = rbac_client
    body = {"code": "4309", "name": "Reset", "parent_id": _padre(rbac)}
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 201
    assert rbac.post("/api/v1/permisos/matriz/reset", 10, "admin", json={"confirm": True}).status_code == 200
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 403


def test_auditoria_de_concesion(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "aprobar").status_code == 201
    eventos = rbac.get(10, "/api/v1/permisos/auditoria", "admin").json()
    assert eventos["total"] >= 1
    concedido = eventos["items"][0]
    assert concedido["resultado"] == "allow"
    assert concedido["motivo"] == "concedido"
    assert concedido["modulo"] == "acct"
    assert concedido["operacion"] == "aprobar"
