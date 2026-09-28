"""Tests SPEC-004 Foundational (T011): ejercicio y factura de A invisibles desde B."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.ar.invoice import Invoice, InvoiceTipo


async def _escenario(db: AsyncSession) -> tuple[int, int]:
    db.add(
        FiscalYear(empresa_id=10, year=2026, date_start=date(2026, 1, 1), date_end=date(2026, 12, 31))
    )
    db.add(
        Invoice(
            empresa_id=10, tipo=InvoiceTipo.emitida, ejercicio=2026, numero_seq=1,
            nif_tercero="B12345678", fecha=date(2026, 3, 15),
            base=Decimal("100.0000"), cuota_iva=Decimal("21.0000"), total=Decimal("121.0000"),
        )
    )
    await db.flush()
    return 10, 20


async def test_ejercicio_de_a_no_visible_desde_b(db_session: AsyncSession) -> None:
    a, b = await _escenario(db_session)
    assert await db_session.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == a, FiscalYear.year == 2026)
    ) is not None
    assert await db_session.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == b, FiscalYear.year == 2026)
    ) is None


async def test_factura_de_a_no_visible_desde_b(db_session: AsyncSession) -> None:
    a, b = await _escenario(db_session)
    assert await db_session.scalar(
        select(Invoice).where(Invoice.empresa_id == a, Invoice.numero_seq == 1)
    ) is not None
    assert await db_session.scalar(
        select(Invoice).where(Invoice.empresa_id == b, Invoice.numero_seq == 1)
    ) is None
