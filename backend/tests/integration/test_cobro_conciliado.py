"""Bank reconciliation collection tests (T030a = T023a).

FR-007 / SPEC-013: a movement (movimiento_id) from the bank reconciliation
confirms the recibo idempotently; a retry returns the same asiento and a manual
collection right after does not duplicate the payment.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.cobro_conciliado import CobroConciliado
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import (
    CobroEstadoError,
    conciliar_cobro,
    confirmar_cobro,
    crear_remesa,
    emitir_remesa,
)
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _remesa_emitida(db_session, empresa_id: int):
    vencimiento = Vencimiento(
        empresa_id=empresa_id,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="R-CONCIL",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=10),
        importe=Decimal("200.0000"),
        estado=EstadoVencimiento.pendiente,
    )
    db_session.add(vencimiento)
    await db_session.flush()
    remesa = await crear_remesa(
        db_session,
        empresa_id,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[vencimiento.id],
    )
    await emitir_remesa(db_session, empresa_id, remesa.id, emisor=EMISOR)
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id, ReciboRemesa.remesa_id == remesa.id
        )
    )
    return remesa, recibo


async def test_conciliacion_confirma_recibo_con_asiento_balanceado(db_session):
    remesa, recibo = await _remesa_emitida(db_session, 13)
    movimiento_id = uuid.uuid4()
    recibo, idempotente = await conciliar_cobro(
        db_session,
        13,
        remesa_id=remesa.id,
        recibo_id=recibo.id,
        movimiento_id=movimiento_id,
        fecha_cobro=date(2026, 10, 15),
    )
    await db_session.commit()

    assert idempotente is False
    assert recibo.estado.value == "cobrado"
    assert recibo.asiento_cobro_id is not None

    asiento = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == recibo.asiento_cobro_id)
    )
    assert asiento is not None and asiento.tipo == JournalEntryTipo.COBRO

    lineas = list(
        (
            await db_session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == asiento.id
                )
            )
        ).all()
    )
    debe = sum((linea.debe for linea in lineas), Decimal(0))
    haber = sum((linea.haber for linea in lineas), Decimal(0))
    assert debe == haber == Decimal("200.0000")

    registro = await db_session.scalar(
        select(CobroConciliado).where(
            CobroConciliado.empresa_id == 13,
            CobroConciliado.movimiento_id == movimiento_id,
        )
    )
    assert registro is not None
    assert registro.recibo_remesa_id == recibo.id


async def test_reintento_idempotente_devuelve_mismo_asiento(db_session):
    remesa, recibo = await _remesa_emitida(db_session, 13)
    movimiento_id = uuid.uuid4()
    await conciliar_cobro(
        db_session, 13, remesa_id=remesa.id, recibo_id=recibo.id, movimiento_id=movimiento_id
    )
    primer_asiento = recibo.asiento_cobro_id

    recibo, idempotente = await conciliar_cobro(
        db_session,
        13,
        remesa_id=remesa.id,
        recibo_id=recibo.id,
        movimiento_id=movimiento_id,
    )
    assert idempotente is True
    assert recibo.asiento_cobro_id == primer_asiento

    n_asientos = await db_session.scalar(
        select(func.count())
        .select_from(JournalEntry)
        .where(JournalEntry.empresa_id == 13, JournalEntry.tipo == JournalEntryTipo.COBRO)
    )
    assert n_asientos == 1


async def test_manual_despues_de_conciliado_no_duplica(db_session):
    remesa, recibo = await _remesa_emitida(db_session, 13)
    await conciliar_cobro(
        db_session,
        13,
        remesa_id=remesa.id,
        recibo_id=recibo.id,
        movimiento_id=uuid.uuid4(),
    )
    with pytest.raises(CobroEstadoError):
        await confirmar_cobro(db_session, 13, remesa.id, recibo.id)