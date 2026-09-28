"""Reclasificacion confirmada + apertura del ejercicio (SPEC-025 T040, US3).

Tras confirmar el trasvase 4300 -> 4310, el cierre de 2025 (SPEC-004) y la
apertura de 2026 (SPEC-009) se generan sin descuadre y los asientos se
sustentan en las cuentas del nuevo catalogo.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado
from services.cycle.apertura import generar_asiento_apertura

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


def _neto(ns, empresa_id: int, code: str) -> str:
    async def _op(session):
        from sqlalchemy import func

        from models.acct.account_plan import AccountPlan

        cuenta = await session.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
            )
        )
        assert cuenta is not None
        neto = await session.scalar(
            select(
                func.coalesce(
                    func.sum(JournalEntryLine.debe - JournalEntryLine.haber), 0
                )
            )
            .join(
                JournalEntry,
                JournalEntry.id == JournalEntryLine.journal_entry_id,
            )
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.account_id == cuenta,
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.estado == JournalEntryEstado.POSTED,
            )
        )
        from decimal import Decimal

        return Decimal(neto)

    return ns.run(ns.consultar(_op))


def test_trasvase_y_apertura_cuadran(catalogo_client):
    ns = catalogo_client

    destino_id = ns.post("/api/v1/catalogo/versiones", json=BODY_DESTINO).json()["id"]

    ns.asiento(
        10,
        date(2025, 6, 30),
        "Cobro 2025",
        [
            {"account_id": ns.cuenta(10, "4300"), "debit": "12500.0000", "credit": "0"},
            {"account_id": ns.cuenta(10, "1110"), "debit": "0", "credit": "12500.0000"},
        ],
    )
    ns.asiento(
        10,
        date(2025, 7, 15),
        "Inmovilizado",
        [
            {"account_id": ns.cuenta(10, "2100"), "debit": "12500.0000", "credit": "0"},
            {"account_id": ns.cuenta(10, "4000"), "debit": "0", "credit": "12500.0000"},
        ],
    )

    preview = ns.get(
        "/api/v1/catalogo/reclasificar/preview",
        version_id=destino_id,
        ejercicio=2025,
    ).json()
    assert preview["total_importe"] == "12500.0000"
    assert [i["codigo_origen"] for i in preview["items"]] == ["4300"]
    assert preview["items"][0]["codigo_destino"] == "4310"

    confirm = ns.post(
        "/api/v1/catalogo/reclasificar/confirmar",
        json={"version_id": destino_id, "ejercicio": 2025, "items": None},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["reclasificaciones"] == 1
    assert confirm.json()["asientos"][0]["cuadre"] is True

    assert _neto(ns, 10, "4300") == 0
    assert _neto(ns, 10, "4310") == 12500

    ns.marcar_cerrado(10, 2025)

    async def _aperturar(session):
        session.add(
            EjercicioContable(
                empresa_id=10,
                ejercicio=2026,
                fecha_inicio=date(2026, 1, 1),
                fecha_fin=date(2026, 12, 31),
                estado=EjercicioEstado.abierto,
            )
        )
        await session.flush()
        return await generar_asiento_apertura(
            session, empresa_id=10, ejercicio_destino=2026, actor="test"
        )

    resultado = ns.run(ns.mutar(_aperturar))
    assert resultado["estado"] == "con_apertura"
    assert resultado["importe_total_debe"] == "12500.0000"
    assert resultado["total_lineas"] == 2

    async def _asiento_apertura(session):
        import uuid as _uuid

        entry = await session.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == 10,
                JournalEntry.id == _uuid.UUID(resultado["asiento_id"]),
            )
        )
        assert entry is not None
        assert entry.estado == JournalEntryEstado.POSTED
        assert entry.tipo.value == "OPENING"
        filas = (
            await session.scalars(
                select(JournalEntryLine)
                .where(
                    JournalEntryLine.empresa_id == 10,
                    JournalEntryLine.journal_entry_id == entry.id,
                )
                .order_by(JournalEntryLine.line_no)
            )
        ).all()
        assert len(filas) == 2
        assert sum((f.debe for f in filas), 0) == sum((f.haber for f in filas), 0)
        por_cuenta = {f.cuenta: f for f in filas}
        assert por_cuenta["2100"].debe == 12500
        assert por_cuenta["2100"].haber == 0
        assert por_cuenta["1110"].haber == 12500
        assert por_cuenta["1110"].debe == 0
        return {f.cuenta for f in filas}

    cuentas_apertura = ns.run(ns.consultar(_asiento_apertura))
    assert cuentas_apertura == {"2100", "1110"}

    for code, estado in (("2100", "igual"), ("1110", "igual"), ("4310", "nueva")):
        filas = ns.get(
            "/api/v1/catalogo/cuentas", version_id=destino_id, q=code
        ).json()["items"]
        assert any(f["codigo_version"] == code and f["estado"] == estado for f in filas)

    vigente = ns.get("/api/v1/catalogo/vigente", fecha="2026-06-01").json()
    assert vigente["version_id"] == ns.tokens["ver10"]
