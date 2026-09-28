"""Tests SPEC-004 US4 (T039/T040/T041): precisión, correlatividad e inmutabilidad."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.invoice import InvoiceTipo
from models.iam.company import Company
from services.invoicing.invoice_service import FacturaError, crear_factura


async def _empresa(db: AsyncSession, company_id: int = 10) -> None:
    db.add(
        Company(company_id=company_id, nif=f"T{company_id:08d}", razon_social="E SL")
    )
    await db.flush()


async def _factura(db: AsyncSession, **kw) -> object:
    base = {"empresa_id": 10, "tipo": InvoiceTipo.emitida, "ejercicio": 2026,
            "nif_tercero": "B12345678", "fecha": date(2026, 3, 15),
            "base": "100.0000", "cuota_iva": "21.0000", "actor": "test"}
    base.update(kw)
    return await crear_factura(db, **base)


async def test_precision_exacta_total_igual_base_mas_cuota(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    factura = await _factura(db_session)
    assert factura.total == factura.base + factura.cuota_iva
    assert f"{factura.total:0.4f}" == "121.0000"


async def test_mas_de_4_decimales_rechazado(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    with pytest.raises(FacturaError) as exc:
        await _factura(db_session, base="100.00001")
    assert exc.value.code == "precision_invalida"


async def test_importe_negativo_rechazado(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    with pytest.raises(FacturaError) as exc:
        await _factura(db_session, base="-1.0000")
    assert exc.value.code == "importe_negativo"
