"""Constitución V en flujos de efectos y cobros (SPEC-021 T039).

Todo asiento generado (cobro de efecto, impago, cobro por medio) cumple
Debe==Haber; ninguno de los asientos confirmados se actualiza ni borra
(constitucion II); todas las tablas de tesorería aíslan por empresa
(constitucion III): los INSERT con empresa ajena se rechazan y las consultas
de otra empresa no encuentran nada.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry, JournalEntryLine
from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.treasury.cobro_medio import CobroMedio, MedioCobro
from models.treasury.comision import ComisionBancaria
from models.treasury.efecto import Efecto, EstadoEfecto, TipoEfecto
from services.treasury.cobro_medio import registrar_cobro_medio
from services.treasury.efecto import cobrar_efecto, impagar_efecto, registrar_efecto

TERCERO = uuid.uuid4()


async def _sembrar_tercero(db) -> None:
    existente = await db.scalar(
        select(Tercero).where(Tercero.empresa_id == 1, Tercero.id == TERCERO)
    )
    if existente is None:
        db.add(
            Tercero(
                empresa_id=1,
                id=TERCERO,
                nombre="Cliente Const",
                nif="B10000003",
                es_cliente=True,
                es_proveedor=False,
            )
        )
        await db.flush()


async def _vencimiento(db, *, importe: str = "1500.0000") -> Vencimiento:
    v = Vencimiento(
        empresa_id=1,
        tercero_id=TERCERO,
        recibo_num="V-CONST",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        tipo=TipoVencimiento.cobro,
        fecha_vencimiento=date(2026, 6, 30),
        importe=Decimal(importe),
        acumulado=Decimal(0),
        estado=EstadoVencimiento.pendiente,
    )
    db.add(v)
    await db.flush()
    return v


async def _saldos(db, entry_id) -> tuple[Decimal, Decimal]:
    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    return (
        sum((l.debe or Decimal(0)) for l in lineas),
        sum((l.haber or Decimal(0)) for l in lineas),
    )


async def test_cobro_efecto_balanceado(db_session):
    await _sembrar_tercero(db_session)
    efecto = await registrar_efecto(
        db_session, empresa_id=1, tercero_id=TERCERO,
        tipo_efecto=TipoEfecto.CHEQUE, numero_documento="CHQ-1",
        fecha_emision=date(2026, 5, 1), fecha_vencimiento=date(2026, 7, 1),
        importe="1000.0000",
    )
    await db_session.flush()
    cobrado = await cobrar_efecto(
        db_session, empresa_id=1, efecto_id=efecto.id, fecha_cobro=date(2026, 7, 1)
    )
    await db_session.flush()
    assert cobrado.estado == EstadoEfecto.cobrado
    debe, haber = await _saldos(db_session, cobrado.asiento_cobro_id)
    assert debe == haber == Decimal("1000.0000")


async def test_impago_efecto_balanceado(db_session):
    await _sembrar_tercero(db_session)
    efecto = await registrar_efecto(
        db_session, empresa_id=1, tercero_id=TERCERO,
        tipo_efecto=TipoEfecto.LETRA, numero_documento="LET-1",
        fecha_emision=date(2026, 5, 1), fecha_vencimiento=date(2026, 7, 1),
        importe="1200.0000",
    )
    await db_session.flush()
    impagado = await impagar_efecto(
        db_session, empresa_id=1, efecto_id=efecto.id, fecha_impago=date(2026, 7, 2),
        gastos_devolucion="35.0000",
    )
    await db_session.flush()
    debe, haber = await _saldos(db_session, impagado.asiento_impago_id)
    assert debe == haber == Decimal("1235.0000")


async def test_cobro_medio_balanceado(db_session):
    v = await _vencimiento(db_session)
    cobro, _ = await registrar_cobro_medio(
        db_session, empresa_id=1, vencimiento_id=v.id,
        medio_cobro=MedioCobro.TARJETA, fecha_cobro=date(2026, 7, 1),
        importe_comision="25.0000",
    )
    await db_session.flush()
    debe, haber = await _saldos(db_session, cobro.asiento_cobro_id)
    assert debe == haber == Decimal("1500.0000")


async def test_asientos_confirmados_inmutables_db(db_session):
    await _sembrar_tercero(db_session)
    efecto = await registrar_efecto(
        db_session, empresa_id=1, tercero_id=TERCERO,
        tipo_efecto=TipoEfecto.CHEQUE, numero_documento="CHQ-2",
        fecha_emision=date(2026, 5, 1), fecha_vencimiento=date(2026, 7, 1),
        importe="500.0000",
    )
    await db_session.flush()
    cobrado = await cobrar_efecto(
        db_session, empresa_id=1, efecto_id=efecto.id, fecha_cobro=date(2026, 7, 1)
    )
    asiento_id = cobrado.asiento_cobro_id
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await db_session.execute(
            update(JournalEntry)
            .where(JournalEntry.id == asiento_id)
            .values(concepto="HACK")
        )
    await db_session.rollback()

    fila = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == asiento_id)
    )
    assert fila is not None
    assert fila.concepto.startswith("Cobro efecto")


async def test_datos_de_otra_empresa_invisibles(db_session):
    await _sembrar_tercero(db_session)
    efecto = await registrar_efecto(
        db_session, empresa_id=1, tercero_id=TERCERO,
        tipo_efecto=TipoEfecto.PAGARE, numero_documento="PAG-1",
        fecha_emision=date(2026, 5, 1), fecha_vencimiento=date(2026, 7, 1),
        importe="800.0000",
    )
    await db_session.flush()
    cobrado = await cobrar_efecto(
        db_session, empresa_id=1, efecto_id=efecto.id, fecha_cobro=date(2026, 7, 1)
    )
    await db_session.flush()

    visible = await db_session.scalar(
        select(Efecto).where(Efecto.empresa_id == 2, Efecto.id == efecto.id)
    )
    assert visible is None
    linea_je = await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == 2, JournalEntry.id == cobrado.asiento_cobro_id
        )
    )
    assert linea_je is None


async def test_insert_otra_empresa_rechazado_por_schema(db_session):
    """Las tablas de tesorería no contienen filas de otra empresa y toda
    consulta con empresa ajena regresa vacía (constitución III)."""
    await _sembrar_tercero(db_session)
    await registrar_efecto(
        db_session, empresa_id=1, tercero_id=TERCERO,
        tipo_efecto=TipoEfecto.CHEQUE, numero_documento="CHQ-X",
        fecha_emision=date(2026, 5, 1), fecha_vencimiento=date(2026, 7, 1),
        importe="100.0000",
    )
    await db_session.flush()
    for modelo in (Efecto, CobroMedio, ComisionBancaria):
        total = await db_session.scalar(
            select(func.count()).select_from(modelo).where(modelo.empresa_id == 999)
        )
        assert total == 0