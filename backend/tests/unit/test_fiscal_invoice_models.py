"""Tests SPEC-004 Foundational (T010): constraints de fiscal_year e invoice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.ar.invoice import Invoice, InvoiceTipo


def _ejercicio(db: AsyncSession, empresa_id: int = 10, year: int = 2026) -> FiscalYear:
    fy = FiscalYear(
        empresa_id=empresa_id,
        year=year,
        date_start=date(year, 1, 1),
        date_end=date(year, 12, 31),
    )
    db.add(fy)
    return fy


def _factura(empresa_id: int = 10, numero: int = 1) -> Invoice:
    return Invoice(
        empresa_id=empresa_id,
        tipo=InvoiceTipo.emitida,
        ejercicio=2026,
        numero_seq=numero,
        nif_tercero="B12345678",
        fecha=date(2026, 3, 15),
        base=Decimal("100.0000"),
        cuota_iva=Decimal("21.0000"),
        total=Decimal("121.0000"),
    )


async def test_ejercicio_unico_por_empresa(db_session: AsyncSession) -> None:
    _ejercicio(db_session)
    await db_session.flush()
    _ejercicio(db_session)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_ejercicio_mismo_ano_otra_empresa_ok(db_session: AsyncSession) -> None:
    _ejercicio(db_session, empresa_id=10)
    _ejercicio(db_session, empresa_id=20)
    await db_session.flush()


async def test_factura_numero_unico_por_empresa_ejercicio(db_session: AsyncSession) -> None:
    db_session.add(_factura())
    await db_session.flush()
    db_session.add(_factura())
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_factura_mismo_numero_otro_ejercicio_ok(db_session: AsyncSession) -> None:
    una = _factura(numero=1)
    otra = _factura(numero=1)
    otra.ejercicio = 2027
    db_session.add_all([una, otra])
    await db_session.flush()


async def test_factura_check_total_igual_base_mas_cuota(db_session: AsyncSession) -> None:
    mala = _factura()
    mala.total = Decimal("120.0000")
    db_session.add(mala)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_factura_tipos_validos(db_session: AsyncSession) -> None:
    una = _factura(numero=1)
    una.tipo = InvoiceTipo.recibida
    db_session.add_all([una, _factura(numero=2)])
    await db_session.flush()
