"""US2 tenant isolation tests (T038).

Empresa B no ve ni el asiento PRONTO_PAGO ni la condición de A; liquidar un
recibo de A desde B da 404.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.condicion_pronto_pago import CondicionProntoPago
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import crear_remesa
from services.tercero_amend import crear_condicion


async def _preparar_liquidacion(db_session_factory):
    tercero = uuid.uuid4()
    async with db_session_factory() as session:
        vencimiento = Vencimiento(
            empresa_id=52,
            tercero_id=tercero,
            factura_id=None,
            fecha_factura=date(2026, 9, 30),
            recibo_num="R-TENANT",
            iban="ES9121000418450200051332",
            ejercicio=2026,
            fecha_vencimiento=date(2026, 12, 31),
            importe=Decimal("100.0000"),
            estado=EstadoVencimiento.pendiente,
        )
        session.add(vencimiento)
        await session.flush()
        await crear_condicion(
            session, 52, tercero, plazo_dias=20, porcentaje=Decimal("2.00")
        )
        remesa = await crear_remesa(
            session,
            52,
            formato="SEPA_DD",
            tipo_adeudo="CORE",
            vencimiento_ids=[vencimiento.id],
        )
        recibo = await session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == 52, ReciboRemesa.remesa_id == remesa.id
            )
        )
        recibo_id = str(recibo.id)
        await session.commit()
    return recibo_id


async def test_empresa_b_no_accede_a_la_liquidacion_de_a(client, db_session_factory):
    recibo_id = await _preparar_liquidacion(db_session_factory)
    test_client, _, auth = client
    hh = auth["hh"]

    respuesta_a = test_client.post(
        f"/api/v1/recibos/{recibo_id}/liquidar",
        json={"fecha_pago": "2026-10-05"},
        headers=hh(52),
    )
    assert respuesta_a.status_code == 200
    asiento_a = respuesta_a.json()["asiento_id"]

    respuesta_b = test_client.post(
        f"/api/v1/recibos/{recibo_id}/liquidar",
        json={"fecha_pago": "2026-10-05"},
        headers=hh(53),
    )
    assert respuesta_b.status_code == 404
    assert respuesta_b.json()["detail"]["code"] == "recibo_no_encontrado"

    async with db_session_factory() as session:
        n_asientos_b = await session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.empresa_id == 53,
                JournalEntry.tipo == JournalEntryTipo.PRONTO_PAGO,
            )
        )
        assert n_asientos_b == 0
        n_condiciones_a = await session.scalar(
            select(func.count())
            .select_from(CondicionProntoPago)
            .where(CondicionProntoPago.empresa_id == 52)
        )
        assert n_condiciones_a == 1
        n_condiciones_b = await session.scalar(
            select(func.count())
            .select_from(CondicionProntoPago)
            .where(CondicionProntoPago.empresa_id == 53)
        )
        assert n_condiciones_b == 0
        asiento_a_fila = await session.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == 53,
                JournalEntry.id == uuid.UUID(asiento_a),
            )
        )
        assert asiento_a_fila is None