"""Test exceso de anticipo sobre factura (SPEC-022 T015, US1).

FR-003: si el anticipo supera la factura, el exceso queda como saldo a favor
del tercero (438); no se puede aplicar más importe del saldo pendiente.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.treasury.anticipo import EstadoAnticipo, TipoAnticipo
from services.treasury.anticipo import registrar_anticipo
from services.treasury.liquidacion import (
    AplicacionAnticipo,
    LiquidacionError,
    liquidar_anticipo,
)
from tests.unit.anticipo_support import CLIENTE, sembrar_base


async def test_exceso_queda_como_saldo_a_favor(db_session):
    base = await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=CLIENTE,
        tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1),
        importe="3000.0000",
        concepto="Anticipo",
    )
    await db_session.flush()

    resultado = await liquidar_anticipo(
        db_session,
        empresa_id=1,
        anticipo_id=anticipo.id,
        aplicaciones=[
            AplicacionAnticipo(factura_id=base["factura_venta_id"], importe_aplicado="2000.0000")
        ],
        fecha_aplicacion=date(2026, 6, 1),
    )
    await db_session.flush()

    assert str(resultado["saldo_pendiente"]) == "1000.0000"
    assert anticipo.saldo_pendiente == Decimal("1000.0000")
    assert anticipo.estado == EstadoAnticipo.parcialmente_aplicado


async def test_liquidar_mas_que_el_saldo_rechazado(db_session):
    base = await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=CLIENTE,
        tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1),
        importe="1000.0000",
        concepto="Anticipo",
    )
    await db_session.flush()

    with pytest.raises(LiquidacionError) as excinfo:
        await liquidar_anticipo(
            db_session,
            empresa_id=1,
            anticipo_id=anticipo.id,
            aplicaciones=[
                AplicacionAnticipo(factura_id=base["factura_venta_id"], importe_aplicado="1001.0000")
            ],
            fecha_aplicacion=date(2026, 6, 1),
        )
    assert excinfo.value.code == "importe_supera_saldo"
    assert excinfo.value.status_code == 422
    assert anticipo.saldo_pendiente == Decimal("1000.0000")


async def test_liquidacion_acumulada_supera_saldo_rechazada(db_session):
    base = await sembrar_base(db_session, 1)
    venta2 = Factura(
        empresa_id=1, serie_id=base["serie_id"], numero=3, ejercicio=2026,
        fecha=date(2026, 2, 3), tipo=FacturaTipo.VENTA, tercero_id=CLIENTE,
        importe_total=Decimal("500.0000"), estado=FacturaEstado.emitida,
    )
    db_session.add(venta2)
    await db_session.flush()
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=CLIENTE,
        tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1),
        importe="1000.0000",
        concepto="Anticipo",
    )
    await db_session.flush()

    with pytest.raises(LiquidacionError) as excinfo:
        await liquidar_anticipo(
            db_session,
            empresa_id=1,
            anticipo_id=anticipo.id,
            aplicaciones=[
                AplicacionAnticipo(factura_id=base["factura_venta_id"], importe_aplicado="600.0000"),
                AplicacionAnticipo(factura_id=venta2.id, importe_aplicado="500.0000"),
            ],
            fecha_aplicacion=date(2026, 6, 1),
        )
    assert excinfo.value.code == "saldo_insuficiente"
    assert excinfo.value.status_code == 409