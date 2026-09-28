"""SPEC-015 US3 (T036/T042): aislamiento multi-tenant de la auditoria.

La auditoria de A no la ve B; B no puede consultar los eventos de A.
"""

from __future__ import annotations


def test_eventos_de_a_no_visibles_desde_b(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "aprobar").status_code == 201
    assert rbac.get(10, "/api/v1/permisos/auditoria", "admin").json()["total"] == 1
    assert rbac.get(20, "/api/v1/permisos/auditoria", "admin").json()["total"] == 0


def test_denegaciones_no_se_mezclan_entre_empresas(rbac_client) -> None:
    rbac = rbac_client
    # deny en A (READ_ONLY no tiene acct/crear)
    assert rbac.post("/api/v1/accounts", 10, "readonly", json={"code": "4601", "name": "X"}).status_code == 403
    # deny en B (ACCOUNTANT no tiene divisas/ver)
    assert rbac.get(20, "/api/v1/permisos/catalogo", "accountant").status_code == 200

    a = rbac.get(10, "/api/v1/permisos/auditoria", "admin").json()
    b = rbac.get(20, "/api/v1/permisos/auditoria", "admin").json()
    assert a["total"] == 1
    assert b["total"] == 0
    assert a["items"][0]["resultado"] == "deny"
