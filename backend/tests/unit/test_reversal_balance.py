"""REVERSAL asiento balance tests (T039).

Una devolución genera un asiento REVERSAL balanceado enlazado al original:
con gastos Debe 430+626 | Haber 572; sin gastos Debe 430 | Haber 572. El
asiento original del cobro no se modifica (constitución II).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import confirmar_cobro, crear_remesa, emitir_remesa
from services.remittance.refund_r19 import DevolucionImporteError, procesar_devolucion
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _recibo_cobrado(db_session) -> tuple[ReciboRemesa, JournalEntry, Vencimiento]:
    vencimiento = Vencimiento(
        empresa_id=12,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="R-REVERSAL",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=10),
        importe=Decimal("150.0000"),
        estado=EstadoVencimiento.pendiente,
    )
    db_session.add(vencimiento)
    await db_session.flush()
    remesa = await crear_remesa(
        db_session,
        12,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[vencimiento.id],
    )
    _, _, _ = await emitir_remesa(db_session, 12, remesa.id, emisor=EMISOR)
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == 12, ReciboRemesa.remesa_id == remesa.id
        )
    )
    await confirmar_cobro(
        db_session, 12, remesa.id, recibo.id, fecha_cobro=date(2026, 10, 5)
    )
    asiento_original = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == recibo.asiento_cobro_id)
    )
    return recibo, asiento_original, vencimiento


async def _lineas(session, asiento_id):
    return list(
        (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == asiento_id
                )
            )
        ).all()
    )


async def test_reversal_con_gastos_balanceado(db_session):
    recibo, original, _ = await _recibo_cobrado(db_session)
    devolucion = await procesar_devolucion(
        db_session,
        12,
        recibo_id=recibo.id,
        codigo="MD06",
        motivo="mandato rechazado",
        importe=Decimal("150.0000"),
        importe_gastos=Decimal("5.0000"),
        fecha_registro=date(2026, 10, 8),
        identificador_externo="R19:MD06:R-REVERSAL:2026-10-05:15000:500",
    )

    asiento = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == devolucion.asiento_reversal_id)
    )
    assert asiento.tipo == JournalEntryTipo.REVERSAL
    assert asiento.original_id == original.id
    assert asiento.estado.value == "POSTED"

    lineas = await _lineas(db_session, asiento.id)
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    assert debe == haber == Decimal("155.0000")
    assert {l.cuenta for l in lineas if l.debe > 0} == {"430", "626"}
    assert {l.cuenta for l in lineas if l.haber > 0} == {"572"}

    original_lineas = await _lineas(db_session, original.id)
    assert len(original_lineas) == 2
    assert {l.cuenta for l in original_lineas if l.debe > 0} == {"572"}
    assert {l.cuenta for l in original_lineas if l.haber > 0} == {"430"}
    original_recargado = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == original.id)
    )
    assert original_recargado.tipo == JournalEntryTipo.COBRO
    assert original_recargado.estado.value == "POSTED"
    assert original_recargado.concepto == "Cobro recibo R-REVERSAL (remesa 1)"


async def test_reversal_sin_gastos_balanceado(db_session):
    recibo, original, _ = await _recibo_cobrado(db_session)
    devolucion = await procesar_devolucion(
        db_session,
        12,
        recibo_id=recibo.id,
        codigo="AC04",
        motivo="IBAN inválido",
        importe=Decimal("150.0000"),
        importe_gastos=Decimal(0),
        fecha_registro=date(2026, 10, 9),
        identificador_externo="R19:AC04:R-REVERSAL:2026-10-05:15000:0",
    )

    asiento = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == devolucion.asiento_reversal_id)
    )
    lineas = await _lineas(db_session, asiento.id)
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    assert debe == haber == Decimal("150.0000")
    assert {l.cuenta for l in lineas if l.debe > 0} == {"430"}
    assert {l.cuenta for l in lineas if l.haber > 0} == {"572"}

    n_asientos = await db_session.scalar(select(JournalEntry.id).where(JournalEntry.id == original.id))
    assert n_asientos is not None
    original_lineas = await _lineas(db_session, original.id)
    assert sum((l.debe for l in original_lineas), Decimal(0)) == Decimal("150.0000")


async def test_importe_superior_al_cobro_rechazado(db_session):
    recibo, _, _ = await _recibo_cobrado(db_session)
    with pytest.raises(DevolucionImporteError):
        await procesar_devolucion(
            db_session,
            12,
            recibo_id=recibo.id,
            codigo="R-RJCT",
            motivo="rechazo general",
            importe=Decimal("999.0000"),
            fecha_registro=date(2026, 10, 9),
            identificador_externo="R19:R-RJCT:R-REVERSAL:2026-10-05:99900:0",
        )