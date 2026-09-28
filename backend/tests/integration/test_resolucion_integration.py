"""Resolucion historica via API (SPEC-025 T021, FR-003/SC-001).

Una fecha resuelve con su version vigente; tras activar una version nueva la
fecha historica no migra y el fallback auditable funciona en HTTP.
"""

from __future__ import annotations

from datetime import date


def test_resuelve_version_vigente_2025(catalogo_client):
    ns = catalogo_client
    r = ns.get("/api/v1/catalogo/vigente", fecha="2025-11-15")
    assert r.status_code == 200
    datos = r.json()
    assert datos["version_id"] == ns.tokens["ver10"]
    assert datos["resolucion"] == "vigente"
    assert datos["codigo"] == "BASE-2025"


def test_tras_alta_2026_la_historia_no_migra(catalogo_client):
    ns = catalogo_client
    alta = ns.post(
        "/api/v1/catalogo/versiones",
        json={
            "codigo": "PGC-2026",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": None,
            "cuentas": [
                {
                    "operacion": "alta",
                    "codigo": "4310",
                    "nombre": "Clientes pagos",
                    "padre_codigo": "431",
                }
            ],
        },
    )
    assert alta.status_code == 201
    nueva_id = alta.json()["id"]

    activar = ns.post(f"/api/v1/catalogo/versiones/{nueva_id}/activar")
    assert activar.status_code == 200
    assert activar.json()["estado"] == "vigente"

    historica = ns.get("/api/v1/catalogo/vigente", fecha="2025-11-15").json()
    assert historica["version_id"] == ns.tokens["ver10"]
    assert historica["resolucion"] == "vigente"

    actual = ns.get("/api/v1/catalogo/vigente", fecha="2026-03-01").json()
    assert actual["version_id"] == nueva_id
    assert actual["resolucion"] == "vigente"

    cuenta_4000 = ns.cuenta(10, "4000")
    asiento = ns.asiento(
        10,
        date(2025, 5, 1),
        "Uso historico de 4000",
        [
            {"account_id": cuenta_4000, "debit": "10.0000", "credit": "0"},
            {"account_id": ns.cuenta(10, "1110"), "debit": "0", "credit": "10.0000"},
        ],
    )
    assert asiento is not None


def test_fallback_auditable(catalogo_client):
    ns = catalogo_client
    r = ns.get("/api/v1/catalogo/vigente", fecha="2024-05-01")
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

    assert int(ns.run(ns.consultar(_conteo)) or 0) >= 1


def test_fecha_invalida_o_ausente_422(catalogo_client):
    ns = catalogo_client
    invalida = ns.get("/api/v1/catalogo/vigente", fecha="ayer")
    assert invalida.status_code == 422
    assert invalida.json()["detail"]["code"] == "parametro_invalido"

    ausente = ns.get("/api/v1/catalogo/vigente")
    assert ausente.status_code == 422
