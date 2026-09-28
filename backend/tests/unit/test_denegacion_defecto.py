"""SPEC-015 US2 (T023): denegacion por defecto.

Operacion sin fila -> 403 y se registra un evento `sin_permiso`.
"""

from __future__ import annotations


def _padre(rbac):
    resp = rbac.get(10, "/api/v1/accounts/tree", "admin")
    return next(n["id"] for n in resp.json()["nodos"] if n["code"] == "4")


def test_sin_fila_deniega_y_audita(rbac_client) -> None:
    rbac = rbac_client
    antes = rbac.conteo_eventos(10, "deny")
    resp = rbac.post(
        "/api/v1/accounts",
        10,
        "readonly",
        json={"code": "4494", "name": "Denegado", "parent_id": _padre(rbac)},
    )
    assert resp.status_code == 403
    assert rbac.conteo_eventos(10, "deny") == antes + 1

    eventos = rbac.get(10, "/api/v1/permisos/auditoria", "admin", resultado="deny").json()
    ultimo = eventos["items"][0]
    assert ultimo["motivo"] == "sin_permiso"
    assert ultimo["modulo"] == "acct"
    assert ultimo["operacion"] == "crear"


def test_lectura_sin_concesion_tambien_deniega(rbac_client) -> None:
    rbac = rbac_client
    matriz_id = rbac.matriz_id(10, "ACCOUNTANT", "acct", "ver")
    assert matriz_id is not None
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_id}", 10, "admin").status_code == 204
    assert rbac.get(10, "/api/v1/accounts/tree", "accountant").status_code == 403
