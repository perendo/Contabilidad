"""Tests SPEC-011 US1 (T017/T018/T019): cobro vía HTTP, aislamiento y cerrado."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from models.acct.fiscal_year import FiscalYear
from models.ar.vencimiento import EstadoVencimiento, Vencimiento


async def _vencimiento(db_session_factory, empresa_id: int, importe: str = "100.0000") -> str:
    async with db_session_factory() as session:
        v = Vencimiento(
            empresa_id=empresa_id,
            tercero_id=uuid.uuid4(),
            factura_id=None,
            recibo_num="R-HTTP",
            iban="ES9121000418450200051332",
            ejercicio=2026,
            fecha_vencimiento=date(2026, 6, 1),
            importe=Decimal(importe),
            estado=EstadoVencimiento.pendiente,
        )
        session.add(v)
        await session.commit()
        return str(v.id)


async def test_cobro_via_http(client, db_session_factory) -> None:
    test_client, _, auth = client
    hh = auth["hh"]
    vid = await _vencimiento(db_session_factory, 42)
    resp = test_client.post(
        f"/api/v1/vencimientos/{vid}/cobrar",
        json={"fecha": "2026-06-05", "importe": "100.0000"},
        headers=hh(42),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["importe"] == "100.0000"
    detalle = test_client.get(f"/api/v1/vencimientos/{vid}", headers=hh(42))
    assert detalle.json()["estado"] == "cobrado"
    assert detalle.json()["saldo_pendiente"] == "0.0000"
    historial = test_client.get(f"/api/v1/vencimientos/{vid}/cobros", headers=hh(42))
    assert len(historial.json()["items"]) == 1


async def test_cobro_cross_empresa_404(client, db_session_factory) -> None:
    test_client, _, auth = client
    hh = auth["hh"]
    vid = await _vencimiento(db_session_factory, 42)
    resp = test_client.post(
        f"/api/v1/vencimientos/{vid}/cobrar",
        json={"fecha": "2026-06-05", "importe": "10.0000"},
        headers=hh(43),
    )
    assert resp.status_code == 404


async def test_cobro_ejercicio_cerrado_409(client, db_session_factory) -> None:
    test_client, _, auth = client
    hh = auth["hh"]
    async with db_session_factory() as session:
        session.add(
            FiscalYear(
                empresa_id=42, year=2026, date_start=date(2026, 1, 1),
                date_end=date(2026, 12, 31), is_closed=True,
            )
        )
        await session.commit()
    vid = await _vencimiento(db_session_factory, 42)
    resp = test_client.post(
        f"/api/v1/vencimientos/{vid}/cobrar",
        json={"fecha": "2026-06-05", "importe": "10.0000"},
        headers=hh(42),
    )
    assert resp.status_code == 409
