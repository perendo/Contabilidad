"""Tests SPEC-011 (T010/T037/T042): aislamiento y contrato con SPEC-020."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.iam.company import Company
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import crear_remesa
from services.treasury.cobros_pagos import CobroPagoError, registrar_cobro


async def _empresa(db: AsyncSession, cid: int) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()


async def _vencimiento(db: AsyncSession, cid: int, recibo_num: str = "R-1") -> Vencimiento:
    v = Vencimiento(
        empresa_id=cid, tercero_id=uuid.uuid4(), factura_id=None, recibo_num=recibo_num,
        iban="ES9121000418450200051332", ejercicio=2026,
        fecha_vencimiento=date(2026, 6, 1), importe=Decimal("100.0000"),
        estado=EstadoVencimiento.pendiente,
    )
    db.add(v)
    await db.flush()
    return v


async def test_vencimiento_a_invisible_desde_b(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    v = await _vencimiento(db_session, 10)
    assert await db_session.scalar(
        select(Vencimiento).where(Vencimiento.empresa_id == 20, Vencimiento.id == v.id)
    ) is None


async def test_cobro_de_vencimiento_ajeno_rechazado(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    v = await _vencimiento(db_session, 10)
    import pytest

    with pytest.raises(CobroPagoError) as exc:
        await registrar_cobro(
            db_session, empresa_id=20, vencimiento_id=v.id,
            fecha=date(2026, 6, 5), importe="10.0000",
        )
    assert exc.value.code == "vencimiento_no_encontrado"


async def test_remesa_emitida_marca_vencimiento_remesado(db_session: AsyncSession) -> None:
    """T042: el contrato de estados con SPEC-020 queda trazable."""
    await _empresa(db_session, 10)
    v = await _vencimiento(db_session, 10)
    remesa = await crear_remesa(
        db_session, 10, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v.id]
    )
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(ReciboRemesa.remesa_id == remesa.id)
    )
    assert recibo is not None
    assert recibo.vencimiento_id == v.id
    assert recibo.estado.value == "pendiente"
