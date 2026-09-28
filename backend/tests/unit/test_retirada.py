"""Tests SPEC-008 US3 (T033/T034/T035): retirada protegida del tercero."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.iam.company import Company
from services.thirdparty.retirada import (
    RetiradaError,
    borrar_tercero,
    inactivar_tercero,
    verificar_movimientos,
)


async def _empresa(db: AsyncSession, cid: int = 10) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()


async def _tercero(db: AsyncSession, cid: int = 10) -> Tercero:
    t = Tercero(empresa_id=cid, nombre="Cliente", nif=None, es_cliente=True)
    db.add(t)
    await db.flush()
    return t


async def test_borrado_sin_movimientos(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    t = await _tercero(db_session)
    await borrar_tercero(db_session, 10, t.id)
    assert await db_session.scalar(select(Tercero).where(Tercero.id == t.id)) is None


async def test_baja_protegida_con_vencimientos(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    t = await _tercero(db_session)
    db_session.add(
        Vencimiento(
            empresa_id=10, tercero_id=t.id, factura_id=None, recibo_num="R",
            iban="ES9121000418450200051332", ejercicio=2026,
            fecha_vencimiento=date(2026, 6, 1), importe=Decimal("10.0000"),
            estado=EstadoVencimiento.pendiente,
        )
    )
    await db_session.flush()
    tiene, motivo = await verificar_movimientos(db_session, 10, t.id)
    assert tiene is True and motivo == "vencimientos"
    with pytest.raises(RetiradaError) as exc:
        await borrar_tercero(db_session, 10, t.id)
    assert exc.value.code == "tiene_movimientos"


async def test_inactivacion_conserva_historial(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    t = await _tercero(db_session)
    db_session.add(
        Vencimiento(
            empresa_id=10, tercero_id=t.id, factura_id=None, recibo_num="R",
            iban="ES9121000418450200051332", ejercicio=2026,
            fecha_vencimiento=date(2026, 6, 1), importe=Decimal("10.0000"),
            estado=EstadoVencimiento.pendiente,
        )
    )
    await db_session.flush()
    tercero = await inactivar_tercero(db_session, 10, t.id)
    assert tercero.activo is False
    n = await db_session.scalar(
        select(Vencimiento).where(Vencimiento.tercero_id == t.id)
    )
    assert n is not None


async def test_tercero_ajeno_no_encontrado(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    t = await _tercero(db_session, 10)
    with pytest.raises(RetiradaError) as exc:
        await inactivar_tercero(db_session, 20, t.id)
    assert exc.value.code == "tercero_no_encontrado"
    assert t.id is not None
