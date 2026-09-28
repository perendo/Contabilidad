"""Tests SPEC-004 US4 (T041): vínculo factura-asiento único e inmutable."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.ar.invoice import InvoiceTipo
from services.invoicing.invoice_service import (
    FacturaError,
    crear_factura,
    vincular_asiento,
)
from services.journal.entry_service import asentar, crear_borrador
from tests.conftest import crear_empresa


async def _escenario(db: AsyncSession) -> tuple:
    await crear_empresa(db, 10, nif="T00000010", razon_social="Empresa 10 SL")
    await db.flush()
    ids: dict[str, int] = {}
    for codigo in ("4", "43", "430", "4300", "5", "57", "572", "5720"):
        cuenta = AccountPlan(
            tenant_id=10, code=codigo, name=f"C-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=len(codigo) >= 4,
        )
        db.add(cuenta)
        await db.flush()
        ids[codigo] = cuenta.id
    factura = await crear_factura(
        db, empresa_id=10, tipo=InvoiceTipo.emitida, ejercicio=2026,
        nif_tercero="B12345678", fecha=date(2026, 3, 15),
        base="100.0000", cuota_iva="21.0000", actor="test",
    )
    borrador = await crear_borrador(
        db, empresa_id=10, fecha=date(2026, 3, 16), concepto="Factura 1",
        lineas=[
            {"account_id": ids["4300"], "debit": "121.0000", "credit": "0"},
            {"account_id": ids["5720"], "debit": "0", "credit": "121.0000"},
        ],
        actor="test",
    )
    asiento = await asentar(db, empresa_id=10, entry_id=borrador.id, actor="test")
    return factura, asiento


async def test_vinculo_unico_ok(db_session: AsyncSession) -> None:
    factura, asiento = await _escenario(db_session)
    vinculada = await vincular_asiento(
        db_session, empresa_id=10, factura_id=factura.id, asiento_id=asiento.id
    )
    assert vinculada.asiento_id == asiento.id


async def test_revinculo_rechazado(db_session: AsyncSession) -> None:
    factura, asiento = await _escenario(db_session)
    await vincular_asiento(
        db_session, empresa_id=10, factura_id=factura.id, asiento_id=asiento.id
    )
    with pytest.raises(FacturaError) as exc:
        await vincular_asiento(
            db_session, empresa_id=10, factura_id=factura.id, asiento_id=asiento.id
        )
    assert exc.value.code == "vinculo_inmutable"


async def test_asiento_otra_empresa_rechazado(db_session: AsyncSession) -> None:
    factura, _ = await _escenario(db_session)
    with pytest.raises(FacturaError) as exc:
        await vincular_asiento(
            db_session, empresa_id=10, factura_id=factura.id, asiento_id=uuid.uuid4()
        )
    assert exc.value.code == "asiento_no_encontrado"
    assert factura.asiento_id is None
