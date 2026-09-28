"""SPEC-015 US2 (T031): denegacion en endpoints reales.

READ_ONLY frente a crear/editar -> 403; ACCOUNTANT (con concesion) -> 2xx.
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


def test_readonly_denegado_en_escrituras(rbac_client) -> None:
    rbac = rbac_client
    body = {"code": "4309", "name": "Nope", "parent_id": _padre(rbac)}
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 403
    assert rbac.post(
        "/api/v1/journal/entries",
        10,
        "readonly",
        json={"fecha": "2026-01-15", "concepto": "X", "lineas": [{"account_id": 1, "debit": "1", "credit": "1"}]},
    ).status_code == 403


def test_accountant_con_concesion_ejecuta(rbac_client) -> None:
    rbac = rbac_client
    body = {"code": "4309", "name": "Contable", "parent_id": _padre(rbac)}
    creada = rbac.post("/api/v1/accounts", 10, "accountant", json=body)
    assert creada.status_code == 201, creada.text
    account_id = creada.json()["id"]
    editada = rbac.client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"name": "Contable editada"},
        headers=rbac.headers("accountant", 10),
    )
    assert editada.status_code == 200, editada.text


def test_readonly_con_permiso_explicito_ejecuta(rbac_client) -> None:
    rbac = rbac_client
    body = {"code": "4309", "name": "Concedido", "parent_id": _padre(rbac)}
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 201
