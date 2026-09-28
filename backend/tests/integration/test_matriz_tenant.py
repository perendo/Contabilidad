"""SPEC-015 US1 (T014/T022): aislamiento multi-tenant de la matriz.

La matriz de A no aplica en B; un administrador de A no muta la matriz de B.
"""

from __future__ import annotations


def test_matriz_de_a_no_aplica_en_b(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.get(10, "/api/v1/accounts/tree", "accountant").status_code == 200
    assert rbac.get(20, "/api/v1/accounts/tree", "accountant").status_code == 200

    matriz_id = rbac.matriz_id(10, "ACCOUNTANT", "acct", "ver")
    assert matriz_id is not None
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_id}", 10, "admin").status_code == 204

    assert rbac.get(10, "/api/v1/accounts/tree", "accountant").status_code == 403
    assert rbac.get(20, "/api/v1/accounts/tree", "accountant").status_code == 200


def test_admin_de_a_no_revoca_matriz_de_b(rbac_client) -> None:
    rbac = rbac_client
    matriz_b = rbac.matriz_id(20, "READ_ONLY", "acct", "ver")
    assert matriz_b is not None
    # empresa activa A=10, pero la concesion pertenece a B=20 -> 404
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_b}", 10, "admin").status_code == 404
    assert rbac.get(20, "/api/v1/accounts/tree", "readonly").status_code == 200


def test_admin_de_a_no_concede_a_rol_de_b(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        10,
        "admin",
        json={"rol_id": rbac.resolver_rol(20, "READ_ONLY"), "modulo": "acct", "operacion": "aprobar"},
    )
    assert resp.status_code == 422


def test_matriz_de_b_visible_solo_en_b(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.get(10, "/api/v1/permisos/matriz", "admin").json()["items"]
    items_a = {(i["rol"], i["modulo"], i["operacion"]) for i in rbac.get(10, "/api/v1/permisos/matriz", "admin").json()["items"]}
    assert rbac.conceder(20, "READ_ONLY", "acct", "aprobar").status_code == 201
    items_a2 = {(i["rol"], i["modulo"], i["operacion"]) for i in rbac.get(10, "/api/v1/permisos/matriz", "admin").json()["items"]}
    assert items_a == items_a2
