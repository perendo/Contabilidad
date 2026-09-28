"""Tests SPEC-004 US4 (T042/T045): facturas aisladas por empresa a nivel servicio."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.invoice import Invoice, InvoiceTipo
from models.iam.company import Company
from services.invoicing.invoice_service import FacturaError, crear_factura


async def _empresas(db: AsyncSession) -> None:
    for cid in (10, 20):
        db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social="E SL"))
    await db.flush()


async def test_factura_b_inaccesible_desde_a(db_session: AsyncSession) -> None:
    await _empresas(db_session)
    creada = await crear_factura(
        db_session, empresa_id=20, tipo=InvoiceTipo.emitida, ejercicio=2026,
        nif_tercero="B12345678", fecha=date(2026, 3, 15),
        base="10.0000", cuota_iva="2.1000", actor="test",
    )
    assert await db_session.scalar(
        select(Invoice).where(Invoice.empresa_id == 10, Invoice.numero_seq == 1)
    ) is None
    vista_b = await db_session.scalar(
        select(Invoice).where(Invoice.empresa_id == 20, Invoice.id == creada.id)
    )
    assert vista_b is not None and vista_b.total == creada.total


async def test_emitida_y_recibida_con_correlativo_propio(db_session: AsyncSession) -> None:
    await _empresas(db_session)
    emitida = await crear_factura(
        db_session, empresa_id=10, tipo=InvoiceTipo.emitida, ejercicio=2026,
        nif_tercero="A11111111", fecha=date(2026, 1, 15),
        base="100.0000", cuota_iva="21.0000", actor="test",
    )
    recibida = await crear_factura(
        db_session, empresa_id=10, tipo=InvoiceTipo.recibida, ejercicio=2026,
        nif_tercero="B22222222", fecha=date(2026, 1, 16),
        base="50.0000", cuota_iva="10.5000", actor="test",
    )
    assert (emitida.numero_seq, recibida.numero_seq) == (1, 2)
    assert recibida.total == recibida.base + recibida.cuota_iva
    with pytest.raises(FacturaError):
        await crear_factura(
            db_session, empresa_id=10, tipo="otro", ejercicio=2026,
            nif_tercero="B12345678", fecha=date(2026, 1, 17),
            base="1.0000", cuota_iva="0.2100", actor="test",
        )
