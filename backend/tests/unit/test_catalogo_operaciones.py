"""SPEC-015 US1 (T012): catalogo cerrado de operaciones.

Operacion fuera del catalogo -> 422; concesion duplicada -> 409.
"""

from __future__ import annotations


def test_operacion_fuera_de_catalogo_es_422(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        10,
        "admin",
        json={
            "rol_id": rbac.resolver_rol(10, "READ_ONLY"),
            "modulo": "acct",
            "operacion": "operacion_inventada",
        },
    )
    assert resp.status_code == 422


def test_modulo_fuera_de_catalogo_es_422(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        10,
        "admin",
        json={
            "rol_id": rbac.resolver_rol(10, "READ_ONLY"),
            "modulo": "modulo_inventado",
            "operacion": "ver",
        },
    )
    assert resp.status_code == 422


def test_concesion_duplicada_es_409(rbac_client) -> None:
    rbac = rbac_client
    first = rbac.conceder(10, "READ_ONLY", "acct", "aprobar")
    assert first.status_code == 201, first.text
    duplicada = rbac.conceder(10, "READ_ONLY", "acct", "aprobar")
    assert duplicada.status_code == 409


def test_concesion_registra_evento_concedido(rbac_client) -> None:
    rbac = rbac_client
    antes = rbac.conteo_eventos(10, "allow")
    assert rbac.conceder(10, "READ_ONLY", "acct", "configurar").status_code == 201
    assert rbac.conteo_eventos(10, "allow") == antes + 1
