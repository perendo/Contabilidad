"""Devolution re-opening tests (T040).

Al procesar una devolución, el recibo pasa a `devuelto`, el vencimiento vuelve
a `pendiente` y la DevolucionRecibo queda registrada con su código y asiento.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.devolucion import (
    DevolucionRecibo,
    EstadoReclamacion,
)
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa
from services.remittance.emision import confirmar_cobro, crear_remesa, emitir_remesa
from services.remittance.refund_r19 import (
    DevolucionEstadoError,
    procesar_devolucion,
)
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _recibo_cobrado(db_session) -> tuple[ReciboRemesa, Vencimiento]:
    vencimiento = Vencimiento(
        empresa_id=12,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="R-REAPERTURA",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=10),
        importe=Decimal("100.0000"),
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
    return recibo, vencimiento


async def test_devolucion_reaabre_vencimiento(db_session):
    recibo, vencimiento = await _recibo_cobrado(db_session)
    devolucion = await procesar_devolucion(
        db_session,
        12,
        recibo_id=recibo.id,
        codigo="MD01",
        motivo="referencia no encontrada",
        importe=Decimal("100.0000"),
        fecha_registro=date(2026, 10, 7),
        identificador_externo="R19:MD01:R-REAPERTURA:2026-10-05:10000:0",
    )
    await db_session.commit()

    recibo = await db_session.scalar(
        select(ReciboRemesa).where(ReciboRemesa.id == recibo.id)
    )
    vencimiento = await db_session.scalar(
        select(Vencimiento).where(Vencimiento.id == vencimiento.id)
    )
    assert recibo.estado == ReciboEstado.devuelto
    assert recibo.asiento_cobro_id is not None
    assert vencimiento.estado == EstadoVencimiento.pendiente

    devolucion_db = await db_session.scalar(
        select(DevolucionRecibo).where(DevolucionRecibo.id == devolucion.id)
    )
    assert devolucion_db is not None
    assert devolucion_db.codigo == "MD01"
    assert devolucion_db.recibo_remesa_id == recibo.id
    assert devolucion_db.asiento_reversal_id is not None
    assert devolucion_db.estado_reclamacion == EstadoReclamacion.sin_reclamacion
    assert devolucion_db.fecha_cargo_original == vencimiento.fecha_vencimiento


async def test_devolucion_rechazada_si_recibo_no_cobrado(db_session):
    vencimiento = Vencimiento(
        empresa_id=12,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="R-SINCOBRO",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=10),
        importe=Decimal("100.0000"),
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
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == 12, ReciboRemesa.remesa_id == remesa.id
        )
    )
    with pytest.raises(DevolucionEstadoError):
        await procesar_devolucion(
            db_session,
            12,
            recibo_id=recibo.id,
            codigo="AC04",
            motivo="IBAN inválido",
            importe=Decimal("100.0000"),
            fecha_registro=date(2026, 10, 7),
            identificador_externo="R19:AC04:R-SINCOBRO:2026-10-05:10000:0",
        )


async def test_retorno_reprocesado_rechazado(db_session):
    recibo, _ = await _recibo_cobrado(db_session)
    identificador = "R19:R-CUST:R-REAPERTURA:2026-10-05:10000:0"
    await procesar_devolucion(
        db_session,
        12,
        recibo_id=recibo.id,
        codigo="R-CUST",
        motivo="rechazado por deudor",
        importe=Decimal("100.0000"),
        fecha_registro=date(2026, 10, 7),
        identificador_externo=identificador,
    )
    from services.remittance.refund_r19 import RetornoYaProcesadoError

    with pytest.raises(RetornoYaProcesadoError):
        await procesar_devolucion(
            db_session,
            12,
            recibo_id=recibo.id,
            codigo="R-CUST",
            motivo="rechazado por deudor",
            importe=Decimal("100.0000"),
            fecha_registro=date(2026, 10, 8),
            identificador_externo=identificador,
        )
    n_devoluciones = (
        await db_session.scalar(
            select(DevolucionRecibo.id).where(
                DevolucionRecibo.empresa_id == 12,
                DevolucionRecibo.identificador_externo == identificador,
            )
        )
        is not None
    )
    assert n_devoluciones