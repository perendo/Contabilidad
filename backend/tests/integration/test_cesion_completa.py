"""Test integración cesión de cobros completa (SPEC-022 T041, US3).

Flujo HTTP: crear cesión con 2 vencimientos (201), verificar asiento
balanceado (572 + 662 vs 430), notificar (200), saldar (200) y comprobar
que el doble cobro del vencimiento cedido queda bloqueado (409).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from services.treasury.cobros_pagos import CobroPagoError, registrar_cobro


def _crear_cesion(api, empresa_id=10, comision="150.0000"):
    return api.post(
        "/api/v1/cesiones",
        empresa_id=empresa_id,
        json={
            "entidad_financiera": "Banco Factor S.A.",
            "fecha_cesion": "2026-10-01",
            "vencimiento_ids": [str(v) for v in api.vencimientos[empresa_id][:2]],
            "comision": comision,
            "tipo_comision": "IMPORTE_FIJO",
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


def test_flujo_cesion_completo(anticipos_client):
    api = anticipos_client
    r = _crear_cesion(api)
    assert r.status_code == 201, r.text
    body = r.json()
    cesion_id = body["id"]
    assert body["importe_total_cedido"] == "3000.0000"
    assert body["comision"] == "150.0000"
    assert body["importe_neto_recibido"] == "2850.0000"
    assert body["n_vencimientos"] == 2

    debe, haber, ctas = _sumas(api, body["asiento_id"])
    assert debe == haber == Decimal("3000.0000")
    assert ctas["572"] == (Decimal("2850.0000"), 0)
    assert ctas["662"] == (Decimal("150.0000"), 0)
    assert ctas["430"] == (0, Decimal("3000.0000"))

    r = api.post(
        f"/api/v1/cesiones/{cesion_id}/notificar",
        empresa_id=10,
        json={
            "cliente_id": str(api.terceros[10]),
            "medio": "EMAIL",
            "fecha_notificacion": "2026-10-01",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "enviada"

    detalle = api.get(10, f"/api/v1/cesiones/{cesion_id}").json()
    assert len(detalle["vencimientos"]) == 2
    assert all(v["estado"] == "cedido" for v in detalle["vencimientos"])
    assert len(detalle["notificaciones"]) == 1

    r = api.post(
        f"/api/v1/cesiones/{cesion_id}/saldar",
        empresa_id=10,
        json={"fecha_saldado": "2026-11-01"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "saldada"

    vid = api.vencimientos[10][0]
    async def _cobrar(session):
        return await registrar_cobro(
            session, empresa_id=10, vencimiento_id=vid,
            fecha=date(2026, 12, 1), importe="1500.0000",
        )

    try:
        api.run(api.mutar(_cobrar))
        raise AssertionError("El cobro de un vencimiento cedido no debería prosperar")
    except CobroPagoError as exc:
        assert exc.code == "vencimiento_cedido"