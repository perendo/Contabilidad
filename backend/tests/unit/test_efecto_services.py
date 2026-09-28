"""Servicios de cartera de efectos (SPEC-021 T011, T012, T013).

Cobro e impago generan asientos balanceados (constitución I), los estados
finales son inmutables (constitución II, reflejado también a nivel DB) y el
impago reabre los vencimientos del tercero (FR-005).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.treasury.efecto import Efecto, EstadoEfecto, TipoEfecto
from services.treasury.cobros_pagos import registrar_cobro
from services.treasury.efecto import (
    EfectoError,
    cobrar_efecto,
    impagar_efecto,
    registrar_efecto,
)

TERCERO = uuid.uuid4()


async def _sembrar_tercero(db: AsyncSession) -> None:
    existente = await db.scalar(
        select(Tercero).where(Tercero.empresa_id == 1, Tercero.id == TERCERO)
    )
    if existente is None:
        db.add(
            Tercero(
                empresa_id=1,
                id=TERCERO,
                nombre="Cliente Unit",
                nif="B10000002",
                es_cliente=True,
                es_proveedor=False,
            )
        )
        await db.flush()


async def _sumas(db: AsyncSession, entry_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    return (
        sum(l.debe or Decimal(0) for l in lineas),
        sum(l.haber or Decimal(0) for l in lineas),
    )


async def _cuentas(db: AsyncSession, entry_id: uuid.UUID) -> dict[str, tuple[Decimal, Decimal]]:
    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    return {l.cuenta: (l.debe or Decimal(0), l.haber or Decimal(0)) for l in lineas}


async def _efecto(
    db: AsyncSession,
    *,
    numero: str = "CH-0001",
    importe: str = "1000.0000",
    tercero: uuid.UUID = TERCERO,
) -> Efecto:
    await _sembrar_tercero(db)
    return await registrar_efecto(
        db,
        empresa_id=1,
        tercero_id=tercero,
        tipo_efecto=TipoEfecto.CHEQUE,
        numero_documento=numero,
        fecha_emision=date(2026, 5, 1),
        fecha_vencimiento=date(2026, 7, 1),
        importe=importe,
        actor="admin@test",
    )


async def test_registrar_efecto_estado_emitido(db_session):
    e = await _efecto(db_session)
    await db_session.flush()
    assert e.estado == EstadoEfecto.emitido
    assert e.asiento_cobro_id is None
    assert e.asiento_impago_id is None
    n = await db_session.scalar(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.empresa_id == 1)
    )
    assert n == 0


async def test_registrar_efecto_documento_duplicado(db_session):
    await _efecto(db_session, numero="CH-X")
    await db_session.flush()
    with pytest.raises(EfectoError) as excinfo:
        await _efecto(db_session, numero="CH-X")
    assert excinfo.value.code == "documento_duplicado"
    assert excinfo.value.status_code == 409


async def test_registrar_efecto_importe_invalido(db_session):
    with pytest.raises(EfectoError) as excinfo:
        await _efecto(db_session, importe="-5.0000")
    assert excinfo.value.code == "importe_invalido"


async def test_registrar_efecto_fecha_invalida(db_session):
    with pytest.raises(EfectoError) as excinfo:
        await registrar_efecto(
            db_session,
            empresa_id=1,
            tercero_id=TERCERO,
            tipo_efecto=TipoEfecto.CHEQUE,
            numero_documento="CH-F",
            fecha_emision=date(2026, 7, 1),
            fecha_vencimiento=date(2026, 5, 1),
            importe="1000.0000",
        )
    assert excinfo.value.code == "fecha_invalida"


async def test_cobrar_efecto_asiento_balanceado(db_session):
    e = await _efecto(db_session)
    await db_session.flush()
    cobrado = await cobrar_efecto(
        db_session, empresa_id=1, efecto_id=e.id, fecha_cobro=date(2026, 7, 2)
    )
    assert cobrado.estado == EstadoEfecto.cobrado
    assert cobrado.asiento_cobro_id is not None
    debe, haber = await _sumas(db_session, cobrado.asiento_cobro_id)
    assert debe == haber == Decimal("1000.0000")
    asiento = await db_session.get(JournalEntry, cobrado.asiento_cobro_id)
    assert asiento.tipo == JournalEntryTipo.COBRO
    cuentas = await _cuentas(db_session, cobrado.asiento_cobro_id)
    assert cuentas["572"] == (Decimal("1000.0000"), Decimal(0))
    assert cuentas["431"] == (Decimal(0), Decimal("1000.0000"))


async def test_cobrar_efecto_doble_rechazado(db_session):
    e = await _efecto(db_session)
    await db_session.flush()
    await cobrar_efecto(db_session, empresa_id=1, efecto_id=e.id, fecha_cobro=date(2026, 7, 2))
    with pytest.raises(EfectoError) as excinfo:
        await cobrar_efecto(db_session, empresa_id=1, efecto_id=e.id, fecha_cobro=date(2026, 7, 3))
    assert excinfo.value.code == "efecto_estado_no_valido"
    assert excinfo.value.status_code == 409


async def test_impagar_efecto_reversal_balance_con_gastos(db_session):
    e = await _efecto(db_session)
    await db_session.flush()
    impagado = await impagar_efecto(
        db_session,
        empresa_id=1,
        efecto_id=e.id,
        fecha_impago=date(2026, 7, 5),
        gastos_devolucion="35.0000",
        motivo="Impagado por el banco",
    )
    assert impagado.estado == EstadoEfecto.impagado
    assert impagado.asiento_impago_id is not None
    entry_id = impagado.asiento_impago_id
    debe, haber = await _sumas(db_session, entry_id)
    assert debe == haber == Decimal("1035.0000")
    asiento = await db_session.get(JournalEntry, entry_id)
    assert asiento.tipo == JournalEntryTipo.REVERSAL
    cuentas = await _cuentas(db_session, entry_id)
    assert cuentas["431"] == (Decimal("1000.0000"), Decimal(0))
    assert cuentas["626"] == (Decimal("35.0000"), Decimal(0))
    assert cuentas["572"] == (Decimal(0), Decimal("1035.0000"))
    assert impagado.notas and "Impagado por el banco" in impagado.notas


async def test_impagar_efecto_sin_gastos(db_session):
    e = await _efecto(db_session)
    await db_session.flush()
    impagado = await impagar_efecto(
        db_session, empresa_id=1, efecto_id=e.id, fecha_impago=date(2026, 7, 5)
    )
    debe, haber = await _sumas(db_session, impagado.asiento_impago_id)
    assert debe == haber == Decimal("1000.0000")
    cuentas = await _cuentas(db_session, impagado.asiento_impago_id)
    assert "626" not in cuentas


async def test_impago_sobre_efecto_cobrado_rechazado(db_session):
    e = await _efecto(db_session)
    await db_session.flush()
    await cobrar_efecto(db_session, empresa_id=1, efecto_id=e.id, fecha_cobro=date(2026, 7, 2))
    with pytest.raises(EfectoError) as excinfo:
        await impagar_efecto(
            db_session, empresa_id=1, efecto_id=e.id, fecha_impago=date(2026, 7, 5)
        )
    assert excinfo.value.code == "efecto_estado_no_valido"


async def test_impago_reapertura_vencimiento(db_session):
    v = Vencimiento(
        empresa_id=1,
        tercero_id=TERCERO,
        recibo_num="V1",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        tipo=TipoVencimiento.cobro,
        fecha_vencimiento=date(2026, 6, 30),
        importe=Decimal("1200.0000"),
        acumulado=Decimal("0.0000"),
        estado=EstadoVencimiento.pendiente,
    )
    db_session.add(v)
    await db_session.flush()
    await registrar_cobro(
        db_session, empresa_id=1, vencimiento_id=v.id, fecha=date(2026, 6, 30),
        importe="1200.0000",
    )
    assert v.estado == EstadoVencimiento.cobrado

    e = await _efecto(db_session, numero="CH-002", importe="1200.0000")
    await db_session.flush()
    await impagar_efecto(
        db_session, empresa_id=1, efecto_id=e.id, fecha_impago=date(2026, 7, 5)
    )
    await db_session.flush()
    assert v.estado == EstadoVencimiento.pendiente
    assert v.acumulado == Decimal("0.0000")


async def test_efecto_no_encontrado_otra_empresa(db_session):
    e = await _efecto(db_session, numero="CH-003")
    await db_session.flush()
    with pytest.raises(EfectoError) as excinfo:
        await cobrar_efecto(db_session, empresa_id=2, efecto_id=e.id, fecha_cobro=date(2026, 7, 2))
    assert excinfo.value.code == "efecto_no_encontrado"
    assert excinfo.value.status_code == 404


async def test_registrar_efecto_ejercicio_cerrado(db_session):
    db_session.add(
        FiscalYear(
            empresa_id=1,
            year=2026,
            date_start=date(2026, 1, 1),
            date_end=date(2026, 12, 31),
            is_closed=True,
        )
    )
    await db_session.flush()
    with pytest.raises(EfectoError) as excinfo:
        await _efecto(db_session)
    assert excinfo.value.code == "ejercicio_cerrado"


async def test_cobrar_efecto_ejercicio_cerrado(db_session):
    db_session.add(
        FiscalYear(
            empresa_id=1,
            year=2027,
            date_start=date(2027, 1, 1),
            date_end=date(2027, 12, 31),
            is_closed=True,
        )
    )
    await db_session.flush()
    e = await _efecto(db_session, numero="CH-004")
    await db_session.flush()
    with pytest.raises(EfectoError) as excinfo:
        await cobrar_efecto(db_session, empresa_id=1, efecto_id=e.id, fecha_cobro=date(2027, 1, 15))
    assert excinfo.value.code == "ejercicio_cerrado"


async def test_efecto_cobrado_inmutable_db(db_session):
    e = await _efecto(db_session, numero="CH-IMM")
    await db_session.flush()
    await cobrar_efecto(db_session, empresa_id=1, efecto_id=e.id, fecha_cobro=date(2026, 7, 2))
    e.estado = EstadoEfecto.impagado
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_efecto_cobrado_no_borrable_db(db_session):
    e = await _efecto(db_session, numero="CH-DEL")
    await db_session.flush()
    await cobrar_efecto(db_session, empresa_id=1, efecto_id=e.id, fecha_cobro=date(2026, 7, 2))
    await db_session.delete(e)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()