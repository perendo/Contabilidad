"""Test liquidación de anticipo de proveedor (SPEC-022 T025, US2).

Al liquidar el anticipo contra la factura de compra se crea un asiento
Debe 410 | Haber 407 (o 408) con Debe == Haber y se actualiza el saldo.
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
    PROVEEDOR,
    cuentas,
    sembrar_base,
    sumas,
)


async def test_liquidacion_proveedor_asiento_balanceado(db_session):
    base = await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=PROVEEDOR,
        tipo=TipoAnticipo.PROVEEDOR,
        fecha=date(2026, 3, 1),
        importe="2500.0000",
        concepto="Anticipo compra",
    )
    await db_session.flush()

    resultado = await liquidar_anticipo(
        db_session,
        empresa_id=1,
        anticipo_id=anticipo.id,
        aplicaciones=[
            AplicacionAnticipo(
                factura_id=base["factura_compra_id"], importe_aplicado="2000.0000"
            )
        ],
        fecha_aplicacion=date(2026, 6, 1),
    )
    await db_session.flush()

    assert resultado["liquidaciones_creadas"] == 1
    assert str(resultado["saldo_pendiente"]) == "500.0000"

    liquidacion = await db_session.scalar(
        select(LiquidacionAnticipo).where(LiquidacionAnticipo.empresa_id == 1)
    )
    asiento = await db_session.get(JournalEntry, liquidacion.asiento_id)
    debe, haber = await sumas(db_session, asiento.id)
    assert debe == haber

    ctas = await cuentas(db_session, asiento.id)
    assert ctas["410"] == (Decimal("2000.0000"), 0)
    assert ctas["407"] == (0, Decimal("2000.0000"))

    assert anticipo.saldo_pendiente == Decimal("500.0000")
    assert anticipo.estado == EstadoAnticipo.parcialmente_aplicado