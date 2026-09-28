"""Escenarios quickstart de anticipos y cesión (SPEC-022 T045).

Reproduce los 6 escenarios de ``quickstart.md``:
1) anticipo de cliente y liquidación; 2) anticipo a proveedor y liquidación;
3) cesión factoring con comisión y notificación; 4) impedir doble cobro;
5) saldo excedente del anticipo; 6) aislamiento multi-empresa.
"""

from __future__ import annotations

import uuid
from datetime import date

from services.treasury.cobros_pagos import CobroPagoError, registrar_cobro


def _sumas(api, asiento_id):
    from decimal import Decimal

    from sqlalchemy import select

    from models.acct.journal import JournalEntryLine

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


def test_escenario1_anticipo_cliente_y_liquidacion(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        json={
            "tercero_id": str(api.terceros[10]),
            "tipo": "CLIENTE",
            "fecha": "2026-09-15",
            "importe": "3000.0000",
            "concepto": "Anticipo curso formación",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["saldo_pendiente"] == "3000.0000"
    assert body["asiento_id"]

    r = api.post(
        f"/api/v1/anticipos/{body['id']}/liquidar",
        json={
            "aplicaciones": [
                {"factura_id": str(api.facturas[10]["venta"]), "importe_aplicado": "2000.0000"}
            ],
            "fecha_aplicacion": "2026-10-01",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["saldo_pendiente"] == "1000.0000"

    debe, haber, ctas = _sumas(api, body["asiento_id"])
    assert debe == haber
    assert ctas["572"] == (__import__("decimal").Decimal("3000.0000"), 0)
    assert ctas["438"] == (0, __import__("decimal").Decimal("3000.0000"))


def test_escenario2_anticipo_proveedor_y_liquidacion(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        json={
            "tercero_id": str(api.proveedores[10]),
            "tipo": "PROVEEDOR",
            "fecha": "2026-09-15",
            "importe": "1500.0000",
            "concepto": "Anticipo material",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["saldo_pendiente"] == "1500.0000"

    r = api.post(
        f"/api/v1/anticipos/{body['id']}/liquidar",
        json={
            "aplicaciones": [
                {"factura_id": str(api.facturas[10]["compra"]), "importe_aplicado": "1500.0000"}
            ],
            "fecha_aplicacion": "2026-10-05",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["saldo_pendiente"] == "0.0000"

    debe, haber, ctas = _sumas(api, body["asiento_id"])
    assert debe == haber
    assert ctas["407"] == (__import__("decimal").Decimal("1500.0000"), 0)
    assert ctas["572"] == (0, __import__("decimal").Decimal("1500.0000"))

    detalle = api.get(10, f"/api/v1/anticipos/{body['id']}").json()
    assert detalle["estado"] == "totalmente_aplicado"


def test_escenario3_cesion_con_notificacion(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/cesiones",
        json={
            "entidad_financiera": "Banco Factor S.A.",
            "fecha_cesion": "2026-10-01",
            "vencimiento_ids": [str(v) for v in api.vencimientos[10][:2]],
            "comision": "150.0000",
            "tipo_comision": "IMPORTE_FIJO",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["comision"] == "150.0000"
    assert body["importe_total_cedido"] == "3000.0000"
    assert body["importe_neto_recibido"] == "2850.0000"

    debe, haber, ctas = _sumas(api, body["asiento_id"])
    assert debe == haber
    assert ctas["662"] == (__import__("decimal").Decimal("150.0000"), 0)

    r = api.post(
        f"/api/v1/cesiones/{body['id']}/notificar",
        json={
            "cliente_id": str(api.terceros[10]),
            "medio": "EMAIL",
            "fecha_notificacion": "2026-10-01",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "enviada"

    detalle = api.get(10, f"/api/v1/cesiones/{body['id']}").json()
    assert all(v["estado"] == "cedido" for v in detalle["vencimientos"])


def test_escenario4_impedir_doble_cobro(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/cesiones",
        json={
            "entidad_financiera": "Banco",
            "fecha_cesion": "2026-10-01",
            "vencimiento_ids": [str(api.vencimientos[10][0])],
            "comision": "0.0000",
            "tipo_comision": "IMPORTE_FIJO",
        },
    )
    assert r.status_code == 201, r.text

    r = api.post(
        f"/api/v1/vencimientos/{api.vencimientos[10][0]}/cobrar",
        json={"fecha": "2026-10-05", "importe": "1500.0000", "cuenta_tesoreria": "5720000"},
    )
    assert r.status_code == 409, r.text

    async def _cobrar(session):
        return await registrar_cobro(
            session, empresa_id=10, vencimiento_id=api.vencimientos[10][0],
            fecha=date(2026, 10, 5), importe="1500.0000",
        )

    try:
        api.run(api.mutar(_cobrar))
        raise AssertionError("El vencimiento cedido no debería poderse cobrar")
    except CobroPagoError as exc:
        assert exc.code == "vencimiento_cedido"


def test_escenario5_saldo_excedente_anticipo(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        json={
            "tercero_id": str(api.terceros[10]),
            "tipo": "CLIENTE",
            "fecha": "2026-09-15",
            "importe": "3000.0000",
            "concepto": "Anticipo curso formación",
        },
    )
    assert r.status_code == 201, r.text
    anticipo_id = r.json()["id"]

    r = api.post(
        f"/api/v1/anticipos/{anticipo_id}/liquidar",
        json={
            "aplicaciones": [
                {"factura_id": str(api.facturas[10]["venta"]), "importe_aplicado": "2000.0000"}
            ],
            "fecha_aplicacion": "2026-10-01",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["saldo_pendiente"] == "1000.0000"

    detalle = api.get(10, f"/api/v1/anticipos/{anticipo_id}").json()
    assert detalle["saldo_pendiente"] == "1000.0000"


def test_escenario6_aislamiento_multi_empresa(anticipos_client):
    api = anticipos_client
    r = api.post(
        "/api/v1/anticipos",
        empresa_id=10,
        json={
            "tercero_id": str(api.terceros[10]),
            "tipo": "CLIENTE",
            "fecha": "2026-09-15",
            "importe": "1000.0000",
            "concepto": "Test",
        },
    )
    assert r.status_code == 201, r.text
    anticipo_id = r.json()["id"]

    r = api.get(20, f"/api/v1/anticipos/{anticipo_id}")
    assert r.status_code == 404