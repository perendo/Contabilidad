"""Quickstart de SPEC-025 (T044): los 5 escenarios de ``quickstart.md``.

Cada escenario corre con un fixture fresco; validan el contrato HTTP exacto
del documento.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine

CSV_ESC3 = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "renombrado,4300,Clientes euros,430,4310\n"
    "alta,4310,Clientes pagos,431,\n"
)


def test_esc1_alta_version_y_vigencia(catalogo_client):
    ns = catalogo_client

    r = ns.post(
        "/api/v1/catalogo/versiones",
        json={
            "codigo": "PGC-2026",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": None,
            "cuentas": [
                {
                    "operacion": "alta",
                    "codigo": "4310",
                    "nombre": "Clientes pagos fraccionados",
                    "padre_codigo": "431",
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["numero_version"] == 2
    assert r.json()["estado"] == "borrador"
    ver_id = r.json()["id"]

    activar = ns.post(f"/api/v1/catalogo/versiones/{ver_id}/activar")
    assert activar.status_code == 200
    assert activar.json()["estado"] == "vigente"

    historica = ns.get("/api/v1/catalogo/vigente", fecha="2025-11-15").json()
    assert historica["version_id"] == ns.tokens["ver10"]
    assert historica["resolucion"] == "vigente"
    assert historica["version_id"] != ver_id

    actual = ns.get("/api/v1/catalogo/vigente", fecha="2026-06-01").json()
    assert actual["version_id"] == ver_id


def test_esc2_cuenta_baja_visible_en_su_contexto(catalogo_client):
    ns = catalogo_client

    entry_id = ns.asiento(
        10,
        date(2025, 5, 1),
        "Cargo a 4000",
        [
            {"account_id": ns.cuenta(10, "4000"), "debit": "500.0000", "credit": "0"},
            {"account_id": ns.cuenta(10, "1110"), "debit": "0", "credit": "500.0000"},
        ],
    )

    alta = ns.post(
        "/api/v1/catalogo/versiones",
        json={
            "codigo": "PGC-2026-B",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
            "cuentas": [
                {
                    "operacion": "baja",
                    "codigo": "4000",
                    "nombre": "Clientes",
                    "destino_codigo": "4300",
                }
            ],
        },
    )
    assert alta.status_code == 201, alta.text
    activar = ns.post(f"/api/v1/catalogo/versiones/{alta.json()['id']}/activar")
    assert activar.status_code == 200, activar.text
    assert activar.json()["estado"] == "vigente"

    contexto_2025 = ns.get("/api/v1/catalogo/vigente", fecha="2025-03-01").json()
    assert contexto_2025["version_id"] == ns.tokens["ver10"]

    cuentas = ns.get("/api/v1/catalogo/cuentas", version_id=ns.tokens["ver10"], q="4000")
    assert cuentas.status_code == 200
    assert any(f["codigo_version"] == "4000" for f in cuentas.json()["items"])

    async def _estado(session):
        entry = await session.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == 10,
                JournalEntry.id == entry_id,
            )
        )
        assert entry is not None
        return entry.estado

    assert ns.run(ns.consultar(_estado)) == JournalEntryEstado.POSTED


def test_esc3_importar_con_mapeo_y_activar(catalogo_client):
    ns = catalogo_client

    r = ns.post(
        "/api/v1/catalogo/importar",
        files={"file": ("catalogo_2026.csv", CSV_ESC3.encode("utf-8"), "text/csv")},
        data={"codigo_version": "PGC-2026-import", "fecha_inicio": "2026-01-01"},
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["nuevas"] == 1
    assert res["renombradas"] == 1
    assert res["suprimidas"] == 0
    assert res["mapeos"] == 1
    assert res["pendientes_mapeo"] == []

    activar = ns.post(f"/api/v1/catalogo/versiones/{res['version_id']}/activar")
    assert activar.status_code == 200
    assert activar.json()["estado"] == "vigente"

    vigente = ns.get("/api/v1/catalogo/vigente", fecha="2026-06-01").json()
    assert vigente["version_id"] == res["version_id"]


def test_esc4_reclasificacion_con_cuadre(catalogo_client):
    ns = catalogo_client

    destino = ns.post(
        "/api/v1/catalogo/versiones",
        json={
            "codigo": "VER-2026",
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
        },
    )
    assert destino.status_code == 201, destino.text
    ver_2026 = destino.json()["id"]

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
        version_id=ver_2026,
        ejercicio=2025,
    )
    assert preview.status_code == 200, preview.text
    items = preview.json()["items"]
    assert len(items) == 1
    assert items[0]["importe"] == "12500.0000"
    assert items[0]["codigo_origen"] == "4300"
    assert items[0]["codigo_destino"] == "4310"

    confirm = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        json={"version_id": ver_2026, "ejercicio": 2025, "items": items},
    )
    assert confirm.status_code == 200, confirm.text
    cuerpo = confirm.json()
    assert cuerpo["reclasificaciones"] == 1
    assert cuerpo["asientos"][0]["cuadre"] is True
    assert cuerpo["total_importe"] == "12500.0000"

    def _neto(code: str) -> str:
        async def _op(session):
            from decimal import Decimal

            from sqlalchemy import func

            cuenta = await session.scalar(
                select(AccountPlan.id).where(
                    AccountPlan.tenant_id == 10, AccountPlan.code == code
                )
            )
            neto = await session.scalar(
                select(
                    func.coalesce(func.sum(JournalEntryLine.debe - JournalEntryLine.haber), 0)
                )
                .join(
                    JournalEntry,
                    JournalEntry.id == JournalEntryLine.journal_entry_id,
                )
                .where(
                    JournalEntryLine.empresa_id == 10,
                    JournalEntryLine.account_id == cuenta,
                    JournalEntry.estado == JournalEntryEstado.POSTED,
                )
            )
            return Decimal(neto)

        return ns.run(ns.consultar(_op))

    suma_origen = _neto("4300") + _neto("4310")
    assert suma_origen == 12500
    assert _neto("4300") == 0
    assert _neto("4310") == 12500


def test_esc5_aislamiento_multi_empresa(catalogo_client):
    ns = catalogo_client

    alta = ns.post(
        "/api/v1/catalogo/versiones",
        json={
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
        },
    )
    assert alta.status_code == 201
    ver_a = alta.json()["id"]

    detalle_b = ns.get(f"/api/v1/catalogo/versiones/{ver_a}", empresa_id=20)
    assert detalle_b.status_code == 404
    assert detalle_b.json()["detail"]["code"] == "version_no_encontrada"

    activar_b = ns.post(
        f"/api/v1/catalogo/versiones/{ver_a}/activar", empresa_id=20
    )
    assert activar_b.status_code == 404

    preview_b = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        empresa_id=20,
        version_id=ver_a,
        ejercicio=2025,
    )
    assert preview_b.status_code == 404

    confirm_b = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        empresa_id=20,
        json={"version_id": ver_a, "ejercicio": 2025, "items": None},
    )
    assert confirm_b.status_code == 404

    cuentas_b = ns.get(
        "/api/v1/catalogo/cuentas", empresa_id=20, version_id=ver_a, q="4310"
    )
    assert cuentas_b.status_code == 404

    vigente_b = ns.get(
        "/api/v1/catalogo/vigente", empresa_id=20, fecha="2025-11-15"
    ).json()
    assert vigente_b["version_id"] == ns.tokens["ver20"]
    assert vigente_b["version_id"] != ver_a
