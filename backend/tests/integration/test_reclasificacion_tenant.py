"""Reclasificacion con aislamiento multi-empresa (SPEC-025 T041, FR-005/SC-005).

La version destino de A es inexistente para B (404) en preview y confirm, y
los asientos ADJUSTMENT creados por A no aparecen nunca en la empresa B.
"""

from __future__ import annotations

from datetime import date

BODY_DESTINO = {
    "codigo": "NORMA-2026",
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-12-31",
    "cuentas": [
        {
            "operacion": "alta",
            "codigo": "4310",
            "nombre": "Clientes pagos",
            "padre_codigo": "431",
        },
        {
            "operacion": "renombrado",
            "codigo": "4300",
            "nombre": "Clientes euros",
            "padre_codigo": "430",
            "destino_codigo": "4310",
        },
    ],
}


def test_preview_y_confirm_no_cruzan_empresas(catalogo_client):
    ns = catalogo_client

    destino_a = ns.post("/api/v1/catalogo/versiones", json=BODY_DESTINO).json()["id"]
    ns.asiento(
        10,
        date(2025, 6, 30),
        "Cobro 2025",
        [
            {"account_id": ns.cuenta(10, "4300"), "debit": "12500.0000", "credit": "0"},
            {"account_id": ns.cuenta(10, "1110"), "debit": "0", "credit": "12500.0000"},
        ],
    )

    preview = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        version_id=destino_a,
        ejercicio=2025,
    )
    assert preview.status_code == 200
    items = preview.json()["items"]
    assert len(items) == 1
    assert items[0]["codigo_origen"] == "4300"
    assert items[0]["codigo_destino"] == "4310"
    assert items[0]["importe"] == "12500.0000"

    preview_b = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        empresa_id=20,
        version_id=destino_a,
        ejercicio=2025,
    )
    assert preview_b.status_code == 404
    assert preview_b.json()["detail"]["code"] == "version_no_encontrada"

    confirm = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        json={"version_id": destino_a, "ejercicio": 2025, "items": items},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["reclasificaciones"] == 1
    assert confirm.json()["asientos"][0]["cuadre"] is True
    assert confirm.json()["total_importe"] == "12500.0000"

    confirm_b = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        empresa_id=20,
        json={"version_id": destino_a, "ejercicio": 2025, "items": None},
    )
    assert confirm_b.status_code == 404


def test_asientos_adjustment_no_pasan_de_empresa(catalogo_client):
    ns = catalogo_client

    def _conteo_adjustment(empresa_id: int):
        async def _op(session):
            from sqlalchemy import func, select

            from models.acct.journal import JournalEntry

            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(JournalEntry)
                    .where(
                        JournalEntry.empresa_id == empresa_id,
                        JournalEntry.tipo == "ADJUSTMENT",
                    )
                )
                or 0
            )

        return _op

    destino_a = ns.post("/api/v1/catalogo/versiones", json=BODY_DESTINO).json()["id"]
    ns.asiento(
        10,
        date(2025, 6, 30),
        "Cobro 2025",
        [
            {"account_id": ns.cuenta(10, "4300"), "debit": "5000.0000", "credit": "0"},
            {"account_id": ns.cuenta(10, "1110"), "debit": "0", "credit": "5000.0000"},
        ],
    )
    res = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        json={"version_id": destino_a, "ejercicio": 2025, "items": None},
    )
    assert res.status_code == 200
    assert res.json()["reclasificaciones"] >= 1

    assert int(ns.run(ns.consultar(_conteo_adjustment(10)))) >= 1
    assert int(ns.run(ns.consultar(_conteo_adjustment(20)))) == 0
