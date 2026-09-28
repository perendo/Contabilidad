"""Test asiento anticipo de proveedor (SPEC-022 T024, US2).

El anticipo a proveedor genera Debe 407 (o 408 si se indica) | Haber 572 con
Debe == Haber y ``saldo_pendiente = importe``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from models.acct.journal import JournalEntry
from models.treasury.anticipo import EstadoAnticipo, TipoAnticipo
from services.treasury.anticipo import registrar_anticipo
from tests.unit.anticipo_support import (
    PROVEEDOR,
    cuentas,
    sembrar_base,
    sumas,
)


async def test_anticipo_proveedor_asiento_balanceado(db_session):
    await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=PROVEEDOR,
        tipo=TipoAnticipo.PROVEEDOR,
        fecha=date(2026, 3, 1),
        importe="3000.0000",
        concepto="Anticipo compra",
    )
    await db_session.flush()

    assert anticipo.estado == EstadoAnticipo.pendiente
    assert anticipo.cuenta_contable == "407"
    assert str(anticipo.saldo_pendiente) == "3000.0000"

    asiento = await db_session.get(JournalEntry, anticipo.asiento_id)
    assert asiento is not None
    debe, haber = await sumas(db_session, asiento.id)
    assert debe == haber

    ctas = await cuentas(db_session, asiento.id)
    assert ctas["407"] == (Decimal("3000.0000"), 0)
    assert ctas["572"] == (0, Decimal("3000.0000"))


async def test_anticipo_proveedor_cuenta_408_si_se_indica(db_session):
    await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=PROVEEDOR,
        tipo=TipoAnticipo.PROVEEDOR,
        fecha=date(2026, 3, 1),
        importe="500.0000",
        concepto="Fondo a cuenta",
        cuenta_contable="408",
    )
    await db_session.flush()

    assert anticipo.cuenta_contable == "408"
    asiento = await db_session.get(JournalEntry, anticipo.asiento_id)
    ctas = await cuentas(db_session, asiento.id)
    assert ctas["408"] == (Decimal("500.0000"), 0)
    assert ctas["572"] == (0, Decimal("500.0000"))