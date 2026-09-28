"""Tests SPEC-011 US1/US2: cobro/pago total y parciales con asiento balanceado."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.iam.company import Company
from services.treasury.cobros_pagos import (
    CobroPagoError,
    registrar_cobro,
    registrar_pago,
)


async def _empresa(db: AsyncSession, cid: int = 10) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()


async def _vencimiento(
    db: AsyncSession, cid: int = 10, importe: str = "100.0000",
    tipo: TipoVencimiento = TipoVencimiento.cobro,
) -> Vencimiento:
    v = Vencimiento(
        empresa_id=cid,
        tercero_id=__import__("uuid").uuid4(),
        factura_id=None,
        recibo_num="R-1",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=date(2026, 6, 1),
        importe=Decimal(importe),
        tipo=tipo,
        estado=EstadoVencimiento.pendiente,
    )
    db.add(v)
    await db.flush()
    return v


async def _balance(db: AsyncSession, entry_id) -> tuple[Decimal, Decimal]:
    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    return (
        sum((l.debe for l in lineas), Decimal(0)),
        sum((l.haber for l in lineas), Decimal(0)),
    )


async def test_cobro_total_saldo_cero_y_estado(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    v = await _vencimiento(db_session)
    op = await registrar_cobro(
        db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="100.0000"
    )
    assert v.saldo_pendiente == Decimal("0.0000")
    assert v.estado == EstadoVencimiento.cobrado
    debe, haber = await _balance(db_session, op.journal_entry_id)
    assert debe == haber == Decimal("100.0000")
    with pytest.raises(CobroPagoError) as exc:
        await registrar_cobro(
            db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 6), importe="1.0000"
        )
    assert exc.value.code == "vencimiento_saldado"


async def test_pago_debe_400_haber_tesoreria(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    v = await _vencimiento(db_session, tipo=TipoVencimiento.pago)
    op = await registrar_pago(
        db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="100.0000"
    )
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == op.journal_entry_id)
        )
    ).all()
    por_cuenta = {l.cuenta: (l.debe, l.haber) for l in lineas}
    assert por_cuenta["400"][0] == Decimal("100.0000")
    assert por_cuenta["572"][1] == Decimal("100.0000")


async def test_override_cuenta_caja(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    v = await _vencimiento(db_session)
    op = await registrar_cobro(
        db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5),
        importe="10.0000", cuenta_tesoreria="570",
    )
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == op.journal_entry_id)
        )
    ).all()
    assert {l.cuenta for l in lineas} == {"570", "430"}


async def test_parciales_acumulan_y_saldan(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    v = await _vencimiento(db_session, importe="300.0000")
    for importe in ("100.0000", "100.0000"):
        await registrar_cobro(
            db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe=importe
        )
    assert v.estado == EstadoVencimiento.parcial
    assert v.acumulado == Decimal("200.0000")
    await registrar_cobro(
        db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="100.0000"
    )
    assert v.estado == EstadoVencimiento.cobrado
    assert v.acumulado == Decimal("300.0000")


async def test_exceso_rechazado(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    v = await _vencimiento(db_session, importe="100.0000")
    with pytest.raises(CobroPagoError) as exc:
        await registrar_cobro(
            db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="100.0001"
        )
    assert exc.value.code == "exceso_importe"


async def test_precision_tercios(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    v = await _vencimiento(db_session, importe="1.0000")
    await registrar_cobro(
        db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="0.3333"
    )
    await registrar_cobro(
        db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="0.3333"
    )
    assert v.estado == EstadoVencimiento.parcial
    await registrar_cobro(
        db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="0.3334"
    )
    assert v.acumulado == Decimal("1.0000")
    assert v.estado == EstadoVencimiento.cobrado


async def test_ejercicio_cerrado_rechaza(db_session: AsyncSession) -> None:
    from models.acct.fiscal_year import FiscalYear

    await _empresa(db_session)
    db_session.add(
        FiscalYear(
            empresa_id=10, year=2026, date_start=date(2026, 1, 1),
            date_end=date(2026, 12, 31), is_closed=True,
        )
    )
    await db_session.flush()
    v = await _vencimiento(db_session)
    with pytest.raises(CobroPagoError) as exc:
        await registrar_cobro(
            db_session, empresa_id=10, vencimiento_id=v.id, fecha=date(2026, 6, 5), importe="10.0000"
        )
    assert exc.value.code == "ejercicio_cerrado"
    n = await db_session.scalar(select(JournalEntry.id).where(JournalEntry.empresa_id == 10))
    assert n is None
