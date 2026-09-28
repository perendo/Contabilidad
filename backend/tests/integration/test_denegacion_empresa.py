"""SPEC-015 US2 (T027/T032): la concesion vale por empresa.

Un rol con permiso en A deniega en B (matriz distinta) y el usuario de A nunca
ve datos de B aunque tenga rol global.
"""

from __future__ import annotations

from sqlalchemy import delete

from models.rbac.matriz_permiso import MatrizPermiso


def _aplanar(nodos):
    pila = list(nodos)
    planos: list[dict] = []
    while pila:
        nodo = pila.pop()
        planos.append(nodo)
        pila.extend(nodo.get("children", []))
    return planos


def _nodos(rbac, empresa_id, token="admin"):
    resp = rbac.get(empresa_id, "/api/v1/accounts/tree", token)
    assert resp.status_code == 200
    return _aplanar(resp.json()["nodos"])


def _padre(rbac, empresa_id, token="admin"):
    return next(n["id"] for n in _nodos(rbac, empresa_id, token) if n["code"] == "430")


def test_concesion_de_a_no_sirve_en_b(rbac_client) -> None:
    rbac = rbac_client

    async def _vaciar_b(session):
        await session.execute(delete(MatrizPermiso).where(MatrizPermiso.empresa_id == 20))

    rbac.run(rbac.mutar(_vaciar_b))
    assert rbac.get(10, "/api/v1/accounts/tree", "accountant").status_code == 200
    assert rbac.get(20, "/api/v1/accounts/tree", "accountant").status_code == 403


def test_datos_de_a_no_visibles_desde_b(rbac_client) -> None:
    rbac = rbac_client
    creada = rbac.post(
        "/api/v1/accounts",
        10,
        "admin",
        json={"code": "4309", "name": "Solo A", "parent_id": _padre(rbac, 10)},
    )
    assert creada.status_code == 201
    codigos_a = {n["code"] for n in _nodos(rbac, 10)}
    codigos_b = {n["code"] for n in _nodos(rbac, 20)}
    assert "4309" in codigos_a
    assert "4309" not in codigos_b
