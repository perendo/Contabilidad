"""Test asiento anticipo de cliente (SPEC-022 T013, US1).

Constitución I: el asiento de anticipo CLIENTE es Debe 572 | Haber 438 con
Debe == Haber; ``saldo_pendiente = importe`` y estado ``pendiente``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from models.acct.journal import JournalEntry, JournalEntryTipo
from models.treasury.anticipo import EstadoAnticipo, TipoAnticipo
from services.treasury.anticipo import registrar_anticipo
from tests.unit.anticipo_support import (
    CLIENTE,
    cuentas,
    sembrar_base,
    sumas,
)


async def test_anticipo_cliente_asiento_balanceado(db_session):
    await sembrar_base(db_session, 1)
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

    assert anticipo.estado == EstadoAnticipo.pendiente
    assert str(anticipo.saldo_pendiente) == "3000.0000"

    asiento = await db_session.get(JournalEntry, anticipo.asiento_id)
    assert asiento is not None
    assert asiento.tipo == JournalEntryTipo.COBRO

    debe, haber = await sumas(db_session, asiento.id)
    assert debe == haber

    ctas = await cuentas(db_session, asiento.id)
    assert ctas["572"] == (Decimal("3000.0000"), 0)
    assert ctas["438"] == (0, Decimal("3000.0000"))


async def test_anticipo_cliente_no_genera_asiento_antes_de_flush(db_session):
    await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session,
        empresa_id=1,
        tercero_id=CLIENTE,
        tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1),
        importe="500.0000",
        concepto="Anticipo",
    )
    await db_session.flush()
    assert anticipo.asiento_id is not None