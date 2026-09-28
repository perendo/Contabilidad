"""Manual collection tests (T030).

FR-007: mark a remesado recibo as collected; a balanced asiento (Debe 572,
Haber 430) is created and the operation cannot run twice (409).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import (
    CobroEstadoError,
    confirmar_cobro,
    crear_remesa,
    emitir_remesa,
)
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _remesa_emitida(db_session, empresa_id: int, importe: str = "150.0000"):
    vencimiento = Vencimiento(
        empresa_id=empresa_id,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="R-COBRO",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=10),
        importe=Decimal(importe),
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
    _, _, _ = await emitir_remesa(db_session, empresa_id, remesa.id, emisor=EMISOR)
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id, ReciboRemesa.remesa_id == remesa.id
        )
    )
    return remesa, recibo, vencimiento


async def test_cobro_manual_cambia_estado_y_crea_asiento_balanceado(db_session):
    remesa, recibo, vencimiento = await _remesa_emitida(db_session, 12)
    remesa, recibo = await confirmar_cobro(
        db_session, 12, remesa.id, recibo.id, fecha_cobro=date(2026, 10, 12)
    )
    await db_session.commit()

    assert recibo.estado.value == "cobrado"
    assert recibo.fecha_cobro == date(2026, 10, 12)
    assert recibo.asiento_cobro_id is not None
    assert vencimiento.estado == EstadoVencimiento.cobrado

    asiento = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == recibo.asiento_cobro_id)
    )
    assert asiento is not None
    assert asiento.tipo == JournalEntryTipo.COBRO
    assert asiento.empresa_id == 12
    assert asiento.estado.value == "POSTED"

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
    assert debe == haber == Decimal("150.0000")

    cuenta_debe = {linea.cuenta for linea in lineas if linea.debe > 0}
    cuenta_haber = {linea.cuenta for linea in lineas if linea.haber > 0}
    assert cuenta_debe == {"572"}
    assert cuenta_haber == {"430"}


async def test_cobro_repetido_rechazado(db_session):
    remesa, recibo, _ = await _remesa_emitida(db_session, 12)
    await confirmar_cobro(db_session, 12, remesa.id, recibo.id)

    with pytest.raises(CobroEstadoError):
        await confirmar_cobro(db_session, 12, remesa.id, recibo.id)

    recibos_cobrados = await db_session.scalar(
        select(func.count())
        .select_from(ReciboRemesa)
        .where(
            ReciboRemesa.empresa_id == 12,
            ReciboRemesa.id == recibo.id,
            ReciboRemesa.estado == "cobrado",
        )
    )
    assert recibos_cobrados == 1


async def test_cobro_solo_un_asiento_por_recibo(db_session):
    remesa, recibo, _ = await _remesa_emitida(db_session, 12)
    await confirmar_cobro(db_session, 12, remesa.id, recibo.id)
    await db_session.commit()

    n_asientos = await db_session.scalar(
        select(func.count())
        .select_from(JournalEntry)
        .where(JournalEntry.empresa_id == 12, JournalEntry.tipo == JournalEntryTipo.COBRO)
    )
    assert n_asientos == 1