"""Alta, listado, detalle y activacion de US1 via HTTP (SPEC-025 T022).

Contrato completo de US1: 201 en el alta, filtros del listado, detalle con
cuentas/mapeos, activacion idempotente, solape 422 y guards RBAC del modulo
``acct`` (403 para operaciones no concedidas).
"""

from __future__ import annotations

BODY_ALTA = {
    "codigo": "PGC-2026",
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-12-31",
    "cuentas": [
        {
            "operacion": "alta",
            "codigo": "4310",
            "nombre": "Clientes pagos",
            "padre_codigo": "431",
        }
    ],
}


def test_alta_detalle_activar_y_listados(catalogo_client):
    ns = catalogo_client

    alta = ns.post("/api/v1/catalogo/versiones", json=BODY_ALTA)
    assert alta.status_code == 201
    creada = alta.json()
    assert creada["numero_version"] == 2
    assert creada["estado"] == "borrador"
    assert creada["codigo"] == "PGC-2026"

    vigentes = ns.get("/api/v1/catalogo/versiones", estado="vigente").json()
    assert [v["codigo"] for v in vigentes["items"]] == ["BASE-2025"]

    borradores = ns.get("/api/v1/catalogo/versiones", estado="borrador").json()
    assert [v["codigo"] for v in borradores["items"]] == ["PGC-2026"]

    desde_2026 = ns.get(
        "/api/v1/catalogo/versiones", fecha_inicio_gte="2026-01-01"
    ).json()
    assert [v["codigo"] for v in desde_2026["items"]] == ["PGC-2026"]
    assert desde_2026["total"] == 1

    detalle = ns.get(f"/api/v1/catalogo/versiones/{creada['id']}").json()
    assert detalle["id"] == creada["id"]
    por_codigo = {c["codigo_version"]: c for c in detalle["cuentas"]}
    assert por_codigo["4310"]["estado"] == "nueva"
    assert por_codigo["4300"]["estado"] == "igual"
    assert any(m["tipo_movimiento"] == "igual" for m in detalle["mapeos"])

    cuentas = ns.get(
        "/api/v1/catalogo/cuentas", version_id=creada["id"], q="Clientes"
    ).json()
    assert len(cuentas["items"]) >= 2
    assert all("clientes" in i["nombre_version"].lower() for i in cuentas["items"])

    activar = ns.post(f"/api/v1/catalogo/versiones/{creada['id']}/activar")
    assert activar.status_code == 200
    assert activar.json()["estado"] == "vigente"

    reactivar = ns.post(f"/api/v1/catalogo/versiones/{creada['id']}/activar")
    assert reactivar.status_code == 200
    assert reactivar.json()["estado"] == "vigente"


def test_solape_de_vigencia_422(catalogo_client):
    ns = catalogo_client
    solape = ns.post(
        "/api/v1/catalogo/versiones",
        json={
            "codigo": "SOLAPA",
            "fecha_inicio": "2025-06-01",
            "fecha_fin": "2026-06-30",
            "cuentas": [],
        },
    )
    assert solape.status_code == 422
    assert solape.json()["detail"]["code"] == "solape_vigencia"


def test_version_no_encontrada_404(catalogo_client):
    ns = catalogo_client
    r = ns.get("/api/v1/catalogo/versiones/00000000-0000-0000-0000-000000000009")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "version_no_encontrada"


def test_rbac_guards_acct(catalogo_client):
    ns = catalogo_client

    lectura = ns.get("/api/v1/catalogo/versiones", token_key="readonly")
    assert lectura.status_code == 200

    alta_ro = ns.post(
        "/api/v1/catalogo/versiones", json=BODY_ALTA, token_key="readonly"
    )
    assert alta_ro.status_code == 403

    alta_cont = ns.post(
        "/api/v1/catalogo/versiones", json=BODY_ALTA, token_key="accountant"
    )
    assert alta_cont.status_code == 201

    import_ro = ns.post(
        "/api/v1/catalogo/importar", json={}, token_key="readonly"
    )
    assert import_ro.status_code == 403

    import_cont = ns.post(
        "/api/v1/catalogo/importar", json={}, token_key="accountant"
    )
    assert import_cont.status_code == 403

    preview_ro = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        token_key="readonly",
        version_id=ns.tokens["ver10"],
        ejercicio=2025,
    )
    assert preview_ro.status_code == 200

    confirmar_ro = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        token_key="readonly",
        json={"version_id": ns.tokens["ver10"], "ejercicio": 2025, "items": None},
    )
    assert confirmar_ro.status_code == 403
