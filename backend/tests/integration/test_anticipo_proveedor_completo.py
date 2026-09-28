"""Test integración anticipo de proveedor completo (SPEC-022 T029, US2).

Flujo HTTP: crear anticipo PROVEEDOR (201), liquidar contra factura de
compra (200), verificar asientos balanceados (407 vs 572 y 410 vs 407).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine


def _crear(api, empresa_id=10, importe="2500.0000"):
    return api.post(
        "/api/v1/anticipos",
        empresa_id=empresa_id,
        json={
            "tercero_id": str(api.proveedores[empresa_id]),
            "tipo": "PROVEEDOR",
            "fecha": "2026-03-01",
            "importe": importe,
            "concepto": "Anticipo compra",
        },
    )


def _sumas(api, asiento_id):
    asiento_uuid = uuid.UUID(str(asiento_id))

    async def _q(session):
        lineas = (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == asiento_uuid
                )
            )
        ).all()
        ctas = {l.cuenta: (l.debe or Decimal(0), l.haber or Decimal(0)) for l in lineas}
        return (
            sum(l.debe or Decimal(0) for l in lineas),
            sum(l.haber or Decimal(0) for l in lineas),
            ctas,
        )

    return api.run(api.consultar(_q))


def test_flujo_anticipo_proveedor_completo(anticipos_client):
    api = anticipos_client
    r = _crear(api)
    assert r.status_code == 201, r.text
    body = r.json()
    anticipo_id = body["id"]
    assert body["saldo_pendiente"] == "2500.0000"

    debe, haber, ctas = _sumas(api, body["asiento_id"])
    assert debe == haber
    assert ctas["407"] == (Decimal("2500.0000"), 0)
    assert ctas["572"] == (0, Decimal("2500.0000"))

    r = api.post(
        f"/api/v1/anticipos/{anticipo_id}/liquidar",
        empresa_id=10,
        json={
            "aplicaciones": [
                {
                    "factura_id": str(api.facturas[10]["compra"]),
                    "importe_aplicado": "2000.0000",
                }
            ],
            "fecha_aplicacion": "2026-06-01",
        },
    )
    assert r.status_code == 200, r.text
    liq = r.json()
    assert liq["saldo_pendiente"] == "500.0000"

    async def _copiar_lineas(session):
        return (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == 10,
                    JournalEntryLine.cuenta.in_(["410", "407"]),
                )
            )
        ).all()

    liquidaciones = api.run(api.consultar(_copiar_lineas))
    lineas_liq = [l for l in liquidaciones if l.journal_entry_id != uuid.UUID(body["asiento_id"])]
    deber_410 = sum(l.debe or Decimal(0) for l in lineas_liq if l.cuenta == "410")
    haber_407 = sum(l.haber or Decimal(0) for l in lineas_liq if l.cuenta == "407")
    assert deber_410 == haber_407 == Decimal("2000.0000")

    detalle = api.get(10, f"/api/v1/anticipos/{anticipo_id}").json()
    assert detalle["saldo_pendiente"] == "500.0000"
    assert detalle["estado"] == "parcialmente_aplicado"