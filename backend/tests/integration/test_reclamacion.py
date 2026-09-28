"""Reclamation management tests (T050).

Reclamaciones sobre una devolución: abrir -> en_curso -> resolver/desestimar.
Una única reclamación activa (abierta o en curso) por devolución; el estado
de la devolución refleja la reclamación.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.devolucion import DevolucionRecibo, EstadoReclamacion, Reclamacion
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import confirmar_cobro, crear_remesa, emitir_remesa
from services.remittance.refund_r19 import (
    ReclamacionActivaError,
    ReclamacionEstadoError,
    procesar_devolucion,
)
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _devolucion_creada(db_session) -> uuid.UUID:
    vencimiento = Vencimiento(
        empresa_id=72,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="R-RECL",
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
        72,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[vencimiento.id],
    )
    _, _, _ = await emitir_remesa(db_session, 72, remesa.id, emisor=EMISOR)
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == 72, ReciboRemesa.remesa_id == remesa.id
        )
    )
    await confirmar_cobro(
        db_session, 72, remesa.id, recibo.id, fecha_cobro=date(2026, 10, 5)
    )
    devolucion = await procesar_devolucion(
        db_session,
        72,
        recibo_id=recibo.id,
        codigo="MD06",
        motivo="mandato rechazado",
        importe=Decimal("100.0000"),
        fecha_registro=date(2026, 10, 8),
        identificador_externo="R19:MD06:R-RECL:2026-10-05:10000:0",
    )
    return devolucion.id


async def test_cielo_completo_de_reclamacion(db_session):
    devolucion_id = await _devolucion_creada(db_session)

    reclamacion = await _gestionar(db_session, devolucion_id, "abrir", "impago injustificado")
    assert reclamacion.estado.value == "abierta"

    reclamacion = await _gestionar(db_session, devolucion_id, "en_curso", "banco investiga")
    assert reclamacion.estado.value == "en_curso"

    reclamacion = await _gestionar(db_session, devolucion_id, "resolver", "devolución confirmada")
    assert reclamacion.estado.value == "resuelta"

    devolucion = await db_session.scalar(
        select(DevolucionRecibo).where(DevolucionRecibo.id == devolucion_id)
    )
    assert devolucion.estado_reclamacion == EstadoReclamacion.resuelta


async def _gestionar(session, devolucion_id, accion, observaciones):
    from services.remittance.refund_r19 import gestionar_reclamacion

    return await gestionar_reclamacion(
        session, 72, devolucion_id, accion, observaciones
    )


async def test_no_hay_dos_reclamaciones_activas(db_session):
    devolucion_id = await _devolucion_creada(db_session)
    await _gestionar(db_session, devolucion_id, "abrir", "primera")
    try:
        await _gestionar(db_session, devolucion_id, "abrir", "segunda")
        assert False, "debería rechazar la segunda reclamación activa"
    except ReclamacionActivaError:
        pass

    reclamaciones = list(
        (
            await db_session.scalars(
                select(Reclamacion).where(Reclamacion.devolucion_id == devolucion_id)
            )
        ).all()
    )
    assert len(reclamaciones) == 1


async def test_transiciones_invalidas_rechazadas(db_session):
    devolucion_id = await _devolucion_creada(db_session)
    try:
        await _gestionar(db_session, devolucion_id, "resolver", "sin abrir")
        assert False
    except ReclamacionEstadoError:
        pass

    await _gestionar(db_session, devolucion_id, "abrir", "ok")
    try:
        await _gestionar(db_session, devolucion_id, "abrir", "otra vez")
        assert False
    except ReclamacionActivaError:
        pass


async def test_desestimacion_db_session(db_session):
    devolucion_id = await _devolucion_creada(db_session)
    reclamacion = await _gestionar(db_session, devolucion_id, "abrir", "inicio")
    reclamacion = await _gestionar(db_session, devolucion_id, "desestimar", "sin base")
    assert reclamacion.estado.value == "desestimada"
    devolucion = await db_session.scalar(
        select(DevolucionRecibo).where(DevolucionRecibo.id == devolucion_id)
    )
    assert devolucion.estado_reclamacion == EstadoReclamacion.desestimada