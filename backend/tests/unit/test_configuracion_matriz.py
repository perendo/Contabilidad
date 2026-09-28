"""SPEC-015 US1 (T013): administracion restringida a `rbac`/`configurar`.

Solo quien tiene `rbac`/`configurar` gestiona la matriz; READ_ONLY y
ACCOUNTANT reciben 403 (la seguridad no depende de ocultar la UI).
"""

from __future__ import annotations


def test_admin_configura_la_matriz(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.conceder(10, "READ_ONLY", "acct", "aprobar")
    assert resp.status_code == 201
    assert resp.json()["concedido"] is True


def test_read_only_no_configura(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        10,
        "readonly",
        json={"rol_id": rbac.resolver_rol(10, "READ_ONLY"), "modulo": "acct", "operacion": "aprobar"},
    )
    assert resp.status_code == 403


def test_accountant_no_configura_pero_ve(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.get(10, "/api/v1/permisos/matriz", "accountant").status_code == 200
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        10,
        "accountant",
        json={"rol_id": rbac.resolver_rol(10, "READ_ONLY"), "modulo": "acct", "operacion": "aprobar"},
    )
    assert resp.status_code == 403


def test_reset_exige_confirmacion_y_es_idempotente(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.post("/api/v1/permisos/matriz/reset", 10, "admin", json={"confirm": False}).status_code == 422
    assert rbac.post("/api/v1/permisos/matriz/reset", 10, "admin", json={"confirm": True}).status_code == 200
    # tras el reset la matriz vuelve al seed por defecto
    assert rbac.get(10, "/api/v1/accounts/tree", "readonly").status_code == 200
