"""Test liquidación de anticipo de cliente (SPEC-022 T014, US1).

Al liquidar contra factura se crea un asiento Debe 430 | Haber 438 con
Debe == Haber, se actualiza ``saldo_pendiente`` y el estado del anticipo
(``parcialmente_aplicado`` si queda remanente).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry
from models.treasury.anticipo import EstadoAnticipo, TipoAnticipo
from models.treasury.liquidacion_anticipo import LiquidacionAnticipo
from services.treasury.anticipo import registrar_anticipo
from services.treasury.liquidacion import AplicacionAnticipo, liquidar_anticipo
from tests.unit.anticipo_support import (
    CLIENTE,
    cuentas,
    sembrar_base,
    sumas,
)


async def test_liquidacion_cliente_asiento_balanceado(db_session):
    base = await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=CLIENTE,
        tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1),
        importe="3000.0000",
        concepto="Anticipo venta",
        actor="admin@test",
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
        actor="admin@test",
    )
    await db_session.flush()

    assert resultado["liquidaciones_creadas"] == 1
    assert str(resultado["saldo_pendiente"]) == "1000.0000"

    liquidaciones = (
        await db_session.scalars(
            select(LiquidacionAnticipo).where(
                LiquidacionAnticipo.empresa_id == 1,
                LiquidacionAnticipo.anticipo_id == anticipo.id,
            )
        )
    ).all()
    assert len(liquidaciones) == 1
    assert liquidaciones[0].importe_aplicado == Decimal("2000.0000")

    asiento = await db_session.get(JournalEntry, liquidaciones[0].asiento_id)
    debe, haber = await sumas(db_session, asiento.id)
    assert debe == haber
    ctas = await cuentas(db_session, asiento.id)
    assert ctas["430"] == (Decimal("2000.0000"), 0)
    assert ctas["438"] == (0, Decimal("2000.0000"))

    assert anticipo.saldo_pendiente == Decimal("1000.0000")
    assert anticipo.estado == EstadoAnticipo.parcialmente_aplicado