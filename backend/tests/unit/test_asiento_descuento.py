"""Liquidation asiento balance tests (T032).

Una liquidación con pronto pago genera Debe==Haber: Debe 572 (neto) + 432/662
(descuento) | Haber 430 (total); sin descuento, solo 572 vs 430 (COBRO).
Precisión 4 decimales sin error de redondeo.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.recibo_remesa import ReciboRemesa
from services.discount import CUENTA_DESCUENTO_GASTO, liquidar_con_descuento
from services.remittance.emision import crear_remesa
from services.tercero_amend import crear_condicion


async def _recibo(db_session, *, importe: str = "100.0000"):
    tercero = uuid.uuid4()
    vencimiento = Vencimiento(
        empresa_id=12,
        tercero_id=tercero,
        factura_id=None,
        fecha_factura=date(2026, 9, 30),
        recibo_num="R-ASIENTO",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=date(2026, 12, 31),
        importe=Decimal(importe),
        estado=EstadoVencimiento.pendiente,
    )
    db_session.add(vencimiento)
    await db_session.flush()
    condicion = await crear_condicion(
        db_session, 12, tercero, plazo_dias=30, porcentaje=Decimal("2.00")
    )
    remesa = await crear_remesa(
        db_session,
        12,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[vencimiento.id],
    )
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == 12, ReciboRemesa.remesa_id == remesa.id
        )
    )
    return recibo, vencimiento, condicion


async def _sumas(session, asiento_id):
    lineas = list(
        (
            await session.scalars(
                select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == asiento_id)
            )
        ).all()
    )
    return lineas, sum((l.debe for l in lineas), Decimal(0)), sum((l.haber for l in lineas), Decimal(0))


async def test_asiento_pronto_pago_balanceado_432(db_session):
    recibo, _, _ = await _recibo(db_session)
    resultado = await liquidar_con_descuento(
        db_session, 12, recibo.id, fecha_pago=date(2026, 10, 5)
    )
    assert resultado.descuento_aplicado
    assert resultado.neto == Decimal("98.0000")
    assert resultado.descuento == Decimal("2.0000")

    lineas, debe, haber = await _sumas(db_session, resultado.asiento_id)
    assert debe == haber == Decimal("100.0000")

    cuentas_debe = {l.cuenta: l.debe for l in lineas if l.debe > 0}
    cuentas_haber = {l.cuenta: l.haber for l in lineas if l.haber > 0}
    assert cuentas_debe["572"] == Decimal("98.0000")
    assert cuentas_debe["432"] == Decimal("2.0000")
    assert cuentas_haber == {"430": Decimal("100.0000")}

    asiento = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == resultado.asiento_id)
    )
    assert asiento.tipo == JournalEntryTipo.PRONTO_PAGO
    assert asiento.estado.value == "POSTED"


async def test_asiento_pronto_pago_cuenta_662(db_session):
    recibo, _, _ = await _recibo(db_session)
    resultado = await liquidar_con_descuento(
        db_session, 12, recibo.id, fecha_pago=date(2026, 10, 5),
        cuenta_descuento=CUENTA_DESCUENTO_GASTO,
    )
    lineas, _, _ = await _sumas(db_session, resultado.asiento_id)
    cuentas_debe = {l.cuenta for l in lineas if l.debe > 0}
    assert cuentas_debe == {"572", "662"}


async def test_asiento_sin_descuento_solo_572_vs_430(db_session):
    recibo, _, _ = await _recibo(db_session)
    resultado = await liquidar_con_descuento(
        db_session, 12, recibo.id, fecha_pago=date(2027, 1, 15)
    )
    assert not resultado.descuento_aplicado
    assert resultado.neto == Decimal("100.0000")
    assert resultado.descuento == Decimal("0.0000")

    lineas, debe, haber = await _sumas(db_session, resultado.asiento_id)
    assert debe == haber == Decimal("100.0000")
    assert {l.cuenta for l in lineas if l.debe > 0} == {"572"}
    assert {l.cuenta for l in lineas if l.haber > 0} == {"430"}

    asiento = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == resultado.asiento_id)
    )
    assert asiento.tipo == JournalEntryTipo.COBRO


async def test_precision_4_decimales_sin_error_de_redondeo(db_session):
    recibo, _, _ = await _recibo(db_session, importe="100.1234")
    resultado = await liquidar_con_descuento(
        db_session, 12, recibo.id, fecha_pago=date(2026, 10, 5)
    )
    _, debe, haber = await _sumas(db_session, resultado.asiento_id)
    assert debe == haber == Decimal("100.1234")
    assert resultado.neto == Decimal("98.1209")
    assert resultado.descuento == Decimal("2.0025")
    assert resultado.neto + resultado.descuento == Decimal("100.1234")