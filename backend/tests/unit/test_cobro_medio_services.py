"""Cobros por medio y comisiones (SPEC-021 T024, T025).

El asiento con comisión es balanceado a tres patas (572 neto + 626 comisión)
y el vencimiento pendiente pasa a cobrado; cobros duplicados/cross-empresa
se rechazan con 409/404.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.acct.fiscal_year import FiscalYear
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.treasury.cobro_medio import CobroMedio, MedioCobro
from models.treasury.comision import ComisionBancaria
from services.treasury.cobro_medio import CobroMedioError, registrar_cobro_medio

TERCERO = uuid.uuid4()


async def _vencimiento(db, *, empresa_id: int = 1, importe: str = "1000.0000",
                       estado=EstadoVencimiento.pendiente,
                       acumulado: Decimal = Decimal("0.0000")) -> Vencimiento:
    v = Vencimiento(
        empresa_id=empresa_id,
        tercero_id=TERCERO,
        recibo_num=f"V-{uuid.uuid4().hex[:6]}",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        tipo=TipoVencimiento.cobro,
        fecha_vencimiento=date(2026, 6, 30),
        importe=Decimal(importe),
        acumulado=acumulado,
        estado=estado,
    )
    db.add(v)
    await db.flush()
    return v


async def _cuentas(db, entry_id):
    from models.acct.journal import JournalEntryLine

    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    return {l.cuenta: (l.debe or Decimal(0), l.haber or Decimal(0)) for l in lineas}


async def test_cobro_transferencia_con_comision(db_session):
    v = await _vencimiento(db_session, importe="1000.0000")
    cobro, comisiones = await registrar_cobro_medio(
        db_session,
        empresa_id=1,
        vencimiento_id=v.id,
        medio_cobro=MedioCobro.TRANSFERENCIA,
        fecha_cobro=date(2026, 7, 1),
        importe_comision="15.0000",
        tipo_comision="TRANSFERENCIA",
        banco_codigo="0001",
        porcentaje="1.50",
        actor="admin@test",
    )
    await db_session.flush()
    assert cobro.importe_total == Decimal("1000.0000")
    assert cobro.importe_comision == Decimal("15.0000")
    assert cobro.importe_neto == Decimal("985.0000")
    assert cobro.asiento_cobro_id is not None
    cuentas = await _cuentas(db_session, cobro.asiento_cobro_id)
    assert cuentas["572"] == (Decimal("985.0000"), Decimal(0))
    assert cuentas["626"] == (Decimal("15.0000"), Decimal(0))
    assert cuentas["430"] == (Decimal(0), Decimal("1000.0000"))
    assert v.estado == EstadoVencimiento.cobrado
    assert v.acumulado == Decimal("1000.0000")
    assert len(comisiones) == 1
    comision = comisiones[0]
    assert comision.importe == Decimal("15.0000")
    assert comision.porcentaje == Decimal("1.50")
    assert comision.banco_codigo == "0001"
    assert comision.cuenta_contable == "626"
    fila = await db_session.scalar(
        select(ComisionBancaria).where(
            ComisionBancaria.cobro_medio_id == cobro.id,
            ComisionBancaria.empresa_id == 1,
        )
    )
    assert fila is not None


async def test_cobro_sin_comision_no_crea_desglose(db_session):
    v = await _vencimiento(db_session, importe="500.0000")
    cobro, comisiones = await registrar_cobro_medio(
        db_session,
        empresa_id=1,
        vencimiento_id=v.id,
        medio_cobro=MedioCobro.TARJETA,
        fecha_cobro=date(2026, 7, 1),
    )
    await db_session.flush()
    assert cobro.importe_neto == Decimal("500.0000")
    assert comisiones == []
    cuentas = await _cuentas(db_session, cobro.asiento_cobro_id)
    assert cuentas["572"] == (Decimal("500.0000"), Decimal(0))
    assert "626" not in cuentas


async def test_cobro_vencimiento_no_pendiente_rechazado(db_session):
    v = await _vencimiento(db_session, estado=EstadoVencimiento.remesado)
    with pytest.raises(CobroMedioError) as excinfo:
        await registrar_cobro_medio(
            db_session,
            empresa_id=1,
            vencimiento_id=v.id,
            medio_cobro=MedioCobro.TARJETA,
            fecha_cobro=date(2026, 7, 1),
        )
    assert excinfo.value.code == "vencimiento_estado_no_valido"
    assert excinfo.value.status_code == 409


async def test_cobro_doble_rechazado(db_session):
    v = await _vencimiento(db_session, importe="700.0000")
    await registrar_cobro_medio(
        db_session, empresa_id=1, vencimiento_id=v.id,
        medio_cobro=MedioCobro.TRANSFERENCIA, fecha_cobro=date(2026, 7, 1),
    )
    with pytest.raises(CobroMedioError) as excinfo:
        await registrar_cobro_medio(
            db_session, empresa_id=1, vencimiento_id=v.id,
            medio_cobro=MedioCobro.TRANSFERENCIA, fecha_cobro=date(2026, 7, 2),
        )
    assert excinfo.value.code == "vencimiento_estado_no_valido"


async def test_cobro_comision_mayor_que_total_rechazada(db_session):
    v = await _vencimiento(db_session, importe="100.0000")
    with pytest.raises(CobroMedioError) as excinfo:
        await registrar_cobro_medio(
            db_session, empresa_id=1, vencimiento_id=v.id,
            medio_cobro=MedioCobro.CAJA, fecha_cobro=date(2026, 7, 1),
            importe_comision="200.0000",
        )
    assert excinfo.value.code == "comision_no_valida"
    assert excinfo.value.status_code == 422


async def test_cobro_vencimiento_otra_empresa_rechazado(db_session):
    v = await _vencimiento(db_session, empresa_id=1, importe="300.0000")
    with pytest.raises(CobroMedioError) as excinfo:
        await registrar_cobro_medio(
            db_session, empresa_id=2, vencimiento_id=v.id,
            medio_cobro=MedioCobro.TARJETA, fecha_cobro=date(2026, 7, 1),
        )
    assert excinfo.value.code == "vencimiento_no_encontrado"
    assert excinfo.value.status_code == 404


async def test_cobro_ejercicio_cerrado(db_session):
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
    v = await _vencimiento(db_session, importe="1000.0000")
    with pytest.raises(CobroMedioError) as excinfo:
        await registrar_cobro_medio(
            db_session, empresa_id=1, vencimiento_id=v.id,
            medio_cobro=MedioCobro.TRANSFERENCIA, fecha_cobro=date(2026, 7, 1),
        )
    assert excinfo.value.code == "ejercicio_cerrado"


async def test_importe_total_nunca_negativo_neto(db_session):
    v = await _vencimiento(db_session, importe="1234.5600")
    cobro, _ = await registrar_cobro_medio(
        db_session, empresa_id=1, vencimiento_id=v.id,
        medio_cobro=MedioCobro.TARJETA, fecha_cobro=date(2026, 7, 1),
        importe_comision="34.5600",
    )
    assert cobro.importe_neto == Decimal("1200.0000")
    registros = await db_session.scalar(
        select(func.count()).select_from(CobroMedio).where(CobroMedio.empresa_id == 1)
    )
    assert registros == 1