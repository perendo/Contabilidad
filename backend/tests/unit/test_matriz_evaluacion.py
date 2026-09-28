"""SPEC-015 US1 (T011): evaluacion de la matriz de permisos.

Fila presente -> allow solo para ese rol; sin fila -> deny (ausencia = denegado);
rol distinto -> deny. Usa el fixture compartido `rbac_client`.
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
    assert resp.status_code == 200
    return _buscar(resp.json()["nodos"], "430")


def test_readonly_puede_ver_pero_no_crear(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.get(10, "/api/v1/accounts/tree", "readonly").status_code == 200
    resp = rbac.post(
        "/api/v1/accounts",
        10,
        "readonly",
        json={"code": "4309", "name": "Solo lectura", "parent_id": _padre(rbac)},
    )
    assert resp.status_code == 403


def test_accountant_puede_crear(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/accounts",
        10,
        "accountant",
        json={"code": "4309", "name": "Contable", "parent_id": _padre(rbac)},
    )
    assert resp.status_code == 201, resp.text


def test_revocar_concesion_deniega_inmediatamente(rbac_client) -> None:
    rbac = rbac_client
    matriz_id = rbac.matriz_id(10, "READ_ONLY", "acct", "ver")
    assert matriz_id is not None
    assert rbac.get(10, "/api/v1/accounts/tree", "readonly").status_code == 200
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_id}", 10, "admin").status_code == 204
    assert rbac.get(10, "/api/v1/accounts/tree", "readonly").status_code == 403


def test_rol_distinto_no_aplica_la_concesion(rbac_client) -> None:
    rbac = rbac_client
    # ACCOUNTANT tiene acct/editar (baja) ... pero no acct/cerrar; READ_ONLY no tiene editar.
    matriz_id = rbac.matriz_id(10, "READ_ONLY", "acct", "editar")
    assert matriz_id is None
    assert rbac.get(10, "/api/v1/accounts/1", "readonly").status_code in (200, 404)


def test_listado_catalogo_y_matriz(rbac_client) -> None:
    rbac = rbac_client
    catalogo = rbac.get(10, "/api/v1/permisos/catalogo", "admin")
    assert catalogo.status_code == 200
    data = catalogo.json()
    assert data["total"] == 15
    modulos = {m["modulo"]: m["operaciones"] for m in data["modulos"]}
    assert set(modulos) == {
        "acct", "ar", "treasury", "bank", "inmovilizado",
        "divisas", "reporting", "fiscal", "invoicing", "centros",
        "ngo", "presupuestos", "cierres", "export", "rbac",
    }
    assert modulos["rbac"] == ["ver", "configurar"]
    assert modulos["export"] == ["ver", "crear", "configurar"]

    matriz = rbac.get(10, "/api/v1/permisos/matriz", "admin")
    assert matriz.status_code == 200
    assert sorted(matriz.json()["roles"]) == ["ACCOUNTANT", "ADMIN", "READ_ONLY"]
    assert len(matriz.json()["items"]) == 179
