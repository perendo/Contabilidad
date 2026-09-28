"""Aislamiento multi-tenant de US1 (SPEC-025 T011, constitucion III).

La version, su detalle, sus cuentas y su resolucion de la empresa A nunca se
leen desde el contexto de la empresa B (404), y cada empresa resuelve su
propia version vigente.
"""

from __future__ import annotations


def test_listado_y_detalle_no_cruzan(catalogo_client):
    ns = catalogo_client
    ver10 = ns.tokens["ver10"]
    ver20 = ns.tokens["ver20"]

    listado_10 = ns.get("/api/v1/catalogo/versiones").json()
    assert listado_10["total"] == 1
    assert listado_10["items"][0]["id"] == ver10

    listado_20 = ns.get("/api/v1/catalogo/versiones", empresa_id=20).json()
    assert listado_20["total"] == 1
    assert listado_20["items"][0]["id"] == ver20

    ok = ns.get(f"/api/v1/catalogo/versiones/{ver10}")
    assert ok.status_code == 200
    assert ok.json()["id"] == ver10

    cruzada = ns.get(f"/api/v1/catalogo/versiones/{ver10}", empresa_id=20)
    assert cruzada.status_code == 404
    assert cruzada.json()["detail"]["code"] == "version_no_encontrada"


def test_vigente_y_cuentas_cross_tenant(catalogo_client):
    ns = catalogo_client
    ver10 = ns.tokens["ver10"]
    ver20 = ns.tokens["ver20"]

    vigente_10 = ns.get("/api/v1/catalogo/vigente", fecha="2025-06-01")
    assert vigente_10.status_code == 200
    assert vigente_10.json()["version_id"] == ver10

    vigente_20 = ns.get(
        "/api/v1/catalogo/vigente", empresa_id=20, fecha="2025-06-01"
    )
    assert vigente_20.status_code == 200
    assert vigente_20.json()["version_id"] == ver20

    cuentas_ok = ns.get("/api/v1/catalogo/cuentas", version_id=ver10, q="4300")
    assert cuentas_ok.status_code == 200
    assert cuentas_ok.json()["items"][0]["codigo_version"] == "4300"

    cuentas_b = ns.get(
        "/api/v1/catalogo/cuentas", empresa_id=20, version_id=ver10, q="4300"
    )
    assert cuentas_b.status_code == 404
    assert cuentas_b.json()["detail"]["code"] == "version_no_encontrada"


def test_activar_y_preview_cross_tenant(catalogo_client):
    ns = catalogo_client
    ver10 = ns.tokens["ver10"]

    activar = ns.post(f"/api/v1/catalogo/versiones/{ver10}/activar", empresa_id=20)
    assert activar.status_code == 404

    preview = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        empresa_id=20,
        version_id=ver10,
        ejercicio=2025,
    )
    assert preview.status_code == 404
    assert preview.json()["detail"]["code"] == "version_no_encontrada"

    confirmar = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        empresa_id=20,
        json={"version_id": ver10, "ejercicio": 2025, "items": None},
    )
    assert confirmar.status_code == 404


def test_resolucion_fallback_audita_y_no_cruza(catalogo_client):
    ns = catalogo_client
    r = ns.get("/api/v1/catalogo/vigente", fecha="2030-01-01")
    assert r.status_code == 200
    assert r.json()["resolucion"] == "fallback"
    assert r.json()["version_id"] == ns.tokens["ver10"]

    async def _conteo(session):
        from sqlalchemy import func, select

        from models.audit.audit_log import AuditLog

        return await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.operacion == "RESOLUCION_FALLBACK",
                AuditLog.empresa_id == 10,
            )
        )

    assert int(ns.run(ns.consultar(_conteo)) or 0) == 1

    r20 = ns.get(
        "/api/v1/catalogo/vigente", empresa_id=20, fecha="2030-01-01"
    )
    assert r20.json()["version_id"] == ns.tokens["ver20"]
