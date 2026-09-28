"""Validación de la constitución en los flujos de anticipos/cesión (SPEC-022 T043).

Constitución I: todo asiento (anticipo, liquidación, cesión) tiene Debe == Haber.
Constitución II: los asientos confirmados (POSTED) son inmutables en DB.
Constitución III: cada tabla nueva filtra/aisla por empresa_id consistentemente.
Constitución: importes como Decimal con 4 decimales.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.treasury.anticipo import Anticipo, TipoAnticipo
from models.treasury.cesion import CesionCobro, TipoComisionCesion
from models.treasury.liquidacion_anticipo import LiquidacionAnticipo
from services.treasury.anticipo import registrar_anticipo
from services.treasury.cesion import registrar_cesion
from services.treasury.liquidacion import AplicacionAnticipo, liquidar_anticipo
from tests.unit.anticipo_support import (
    CLIENTE,
    cuentas,
    sembrar_base,
    sumas,
)


async def _crear_vencimientos(db, empresa_id, tercero_id, n=1) -> list:
    ids = []
    for i in range(n):
        v = Vencimiento(
            empresa_id=empresa_id, tercero_id=tercero_id, recibo_num=f"C-{i}",
            iban="ES9121000418450200051332", ejercicio=2026,
            tipo=TipoVencimiento.cobro, fecha_vencimiento=date(2026, 9, 30),
            importe=Decimal("1500.0000"), acumulado=Decimal("0.0000"),
            estado=EstadoVencimiento.pendiente,
        )
        db.add(v)
        await db.flush()
        ids.append(v.id)
    return ids


async def test_todos_los_asientos_balanceados(db_session):
    base = await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session, empresa_id=1, tercero_id=CLIENTE, tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1), importe="3000.0000", concepto="Anticipo",
    )
    await db_session.flush()
    asiento_anticipo = anticipo.asiento_id

    liq = await liquidar_anticipo(
        db_session, empresa_id=1, anticipo_id=anticipo.id,
        aplicaciones=[
            AplicacionAnticipo(factura_id=base["factura_venta_id"], importe_aplicado="2000.0000")
        ],
        fecha_aplicacion=date(2026, 6, 1),
    )
    assert liq["liquidaciones_creadas"] == 1
    await db_session.flush()
    liquidaciones = (
        await db_session.scalars(
            select(LiquidacionAnticipo).where(
                LiquidacionAnticipo.anticipo_id == anticipo.id
            )
        )
    ).all()
    asiento_liq = liquidaciones[0].asiento_id

    venc_ids = await _crear_vencimientos(db_session, 1, CLIENTE, 2)
    cesion = await registrar_cesion(
        db_session, empresa_id=1, entidad_financiera="Banco",
        fecha_cesion=date(2026, 7, 1), vencimiento_ids=venc_ids,
        comision="100.0000", tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
    )
    await db_session.flush()
    asiento_cesion = cesion.asiento_id

    for asiento_id in (asiento_anticipo, asiento_liq, asiento_cesion):
        debe, haber = await sumas(db_session, asiento_id)
        assert debe == haber, f"Asiento {asiento_id} desbalanceado: {debe} != {haber}"
        assert debe > 0

    ctas_anticipo = await cuentas(db_session, asiento_anticipo)
    assert ctas_anticipo["438"] == (0, Decimal("3000.0000"))
    ctas_cesion = await cuentas(db_session, asiento_cesion)
    assert ctas_cesion["662"] == (Decimal("100.0000"), 0)


async def test_asientos_confirmados_inmutables(db_session):
    await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session, empresa_id=1, tercero_id=CLIENTE, tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1), importe="500.0000", concepto="Anticipo",
    )
    await db_session.flush()
    asiento = await db_session.get(JournalEntry, anticipo.asiento_id)
    assert asiento is not None

    asiento.concepto = "intento de mutación"
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.flush()
    assert "inmutable" in str(excinfo.value)
    await db_session.rollback()


async def test_aislamiento_empresa_en_cada_tabla(db_session):
    first = await sembrar_base(db_session, 1, n_vencimientos=1)
    await sembrar_base(
        db_session, 2, n_vencimientos=1,
        cliente_id=uuid.uuid4(), proveedor_id=uuid.uuid4(),
    )
    a = await registrar_anticipo(
        db_session, empresa_id=1, tercero_id=CLIENTE, tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1), importe="1000.0000", concepto="A",
    )
    cesion = await registrar_cesion(
        db_session, empresa_id=1, entidad_financiera="Banco",
        fecha_cesion=date(2026, 7, 1), vencimiento_ids=first["vencimientos"][:1],
        comision="0.0000", tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
    )
    await db_session.flush()

    de_b = await db_session.scalar(
        select(Anticipo).where(Anticipo.empresa_id == 2)
    )
    assert de_b is None
    de_b = await db_session.scalar(
        select(CesionCobro).where(CesionCobro.empresa_id == 2)
    )
    assert de_b is None
    lista = (
        await db_session.scalars(
            select(JournalEntry).where(
                JournalEntry.empresa_id == 2, JournalEntry.concepto.like("Cesi%")
            )
        )
    ).all()
    assert not lista
    assert a.empresa_id == 1
    assert cesion.empresa_id == 1


async def test_importes_decimal_4_digitos(db_session):
    await sembrar_base(db_session, 1)
    anticipo = await registrar_anticipo(
        db_session, empresa_id=1, tercero_id=CLIENTE, tipo=TipoAnticipo.CLIENTE,
        fecha=date(2026, 3, 1), importe="1234.5678", concepto="Anticipo",
    )
    await db_session.flush()
    assert str(anticipo.importe) == "1234.5678"
    assert str(anticipo.saldo_pendiente) == "1234.5678"