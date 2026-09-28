"""Test integración anticipo de cliente completo (SPEC-022 T022, US1).

Flujo HTTP: crear anticipo (201), liquidar contra factura (200), verificar
asientos balanceados y saldo y que la operación queda auditada.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from models.audit.audit_log import AuditLog
from models.treasury.anticipo import Anticipo
from models.treasury.liquidacion_anticipo import LiquidacionAnticipo


def _crear(api, empresa_id=10):
    return api.post(
        "/api/v1/anticipos",
        empresa_id=empresa_id,
        json={
            "tercero_id": str(api.terceros[empresa_id]),
            "tipo": "CLIENTE",
            "fecha": "2026-03-01",
            "importe": "3000.0000",
            "concepto": "Anticipo venta",
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
        return (
            sum(l.debe or Decimal(0) for l in lineas),
            sum(l.haber or Decimal(0) for l in lineas),
        )

    return api.run(api.consultar(_q))


def test_flujo_anticipo_cliente_completo(anticipos_client):
    api = anticipos_client
    r = _crear(api)
    assert r.status_code == 201, r.text
    body = r.json()
    anticipo_id = body["id"]
    assert body["saldo_pendiente"] == "3000.0000"
    asiento_anticipo = body["asiento_id"]

    r = api.post(
        f"/api/v1/anticipos/{anticipo_id}/liquidar",
        empresa_id=10,
        json={
            "aplicaciones": [
                {
                    "factura_id": str(api.facturas[10]["venta"]),
                    "importe_aplicado": "2000.0000",
                }
            ],
            "fecha_aplicacion": "2026-06-01",
        },
    )
    assert r.status_code == 200, r.text
    liq = r.json()
    assert liq["saldo_pendiente"] == "1000.0000"
    assert liq["liquidaciones_creadas"] == 1

    detalle = api.get(10, f"/api/v1/anticipos/{anticipo_id}").json()
    assert detalle["saldo_pendiente"] == "1000.0000"
    assert detalle["estado"] == "parcialmente_aplicado"
    assert len(detalle["liquidaciones"]) == 1

    debe_a, haber_a = _sumas(api, asiento_anticipo)
    assert debe_a == haber_a == Decimal("3000.0000")

    anticipo_uuid = uuid.UUID(anticipo_id)

    async def _liquidaciones(session):
        return (
            await session.scalars(
                select(LiquidacionAnticipo).where(
                    LiquidacionAnticipo.empresa_id == 10,
                    LiquidacionAnticipo.anticipo_id == anticipo_uuid,
                )
            )
        ).all()

    liquidaciones = api.run(api.consultar(_liquidaciones))
    assert len(liquidaciones) == 1
    asiento_liq = liquidaciones[0].asiento_id
    debe_l, haber_l = _sumas(api, asiento_liq)
    assert debe_l == haber_l == Decimal("2000.0000")

    async def _check_audit(session):
        registros = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.empresa_id == 10,
                    AuditLog.operacion.in_(["REGISTRAR_ANTICIPO", "LIQUIDAR_ANTICIPO"]),
                )
            )
        ).all()
        return [(x.operacion, x.entidad) for x in registros]

    auditoria = api.run(api.consultar(_check_audit))
    assert ("REGISTRAR_ANTICIPO", "anticipo") in auditoria
    assert ("LIQUIDAR_ANTICIPO", "anticipo") in auditoria

    async def _estado(session):
        a = await session.scalar(
            select(Anticipo).where(
                Anticipo.empresa_id == 10, Anticipo.id == anticipo_uuid
            )
        )
        return a

    anticipo_final = api.run(api.consultar(_estado))
    assert str(anticipo_final.saldo_pendiente) == "1000.0000"