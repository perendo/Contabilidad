"""SPEC-015 US3 (T041): auditoria completa y atomicidad.

Denegar y conceder quedan consultables con todos los campos; el evento de un
allow se confirma en la misma transaccion que la operacion de negocio.
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


def test_denegar_y_conceder_quedan_auditados(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.post("/api/v1/accounts", 10, "readonly", json={"code": "4309", "name": "X"}).status_code == 403
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    creada = rbac.post(
        "/api/v1/accounts",
        10,
        "readonly",
        json={"code": "4309", "name": "Ok", "parent_id": _padre(rbac)},
    )
    assert creada.status_code == 201

    eventos = rbac.get(10, "/api/v1/permisos/auditoria", "admin", page_size=100).json()
    assert eventos["total"] >= 3
    pares = {(e["modulo"], e["operacion"], e["resultado"]) for e in eventos["items"]}
    assert ("acct", "crear", "deny") in pares
    assert ("acct", "crear", "allow") in pares


def test_filtros_de_auditoria(rbac_client) -> None:
    rbac = rbac_client
    rbac.post("/api/v1/accounts", 10, "readonly", json={"code": "4703", "name": "X"})
    denegados = rbac.get(10, "/api/v1/permisos/auditoria", "admin", resultado="deny").json()
    assert denegados["total"] == 1
    assert all(e["resultado"] == "deny" for e in denegados["items"])
    por_modulo = rbac.get(10, "/api/v1/permisos/auditoria", "admin", modulo="acct").json()
    assert por_modulo["total"] == 1
    assert rbac.get(10, "/api/v1/permisos/auditoria", "admin", modulo="fiscal").json()["total"] == 0
