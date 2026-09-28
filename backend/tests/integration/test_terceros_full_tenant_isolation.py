"""Tests SPEC-008 Polish (T046/T047): constitución y hardening cross-empresa."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.ar.tercero_subcuenta import TerceroSubcuenta
from services.thirdparty.alta import crear_tercero
from services.thirdparty.retirada import RetiradaError, borrar_tercero
from tests.conftest import sembrar_empresa_pgc


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


async def test_toda_tabla_lleva_empresa_id(db_session: AsyncSession) -> None:
    assert "empresa_id" in Tercero.__table__.columns
    assert "empresa_id" in TerceroSubcuenta.__table__.columns


async def test_inactivar_no_borra_asientos(db_session: AsyncSession) -> None:
    from datetime import date
    from decimal import Decimal

    from models.ar.vencimiento import EstadoVencimiento, Vencimiento
    from services.thirdparty.retirada import inactivar_tercero

    await sembrar_empresa_pgc(db_session, 10, nif="T00000010", razon_social="E10 SL")
    t = await crear_tercero(
        db_session, empresa_id=10, nif="12345678Z", razon_social="C", es_cliente=True
    )
    db_session.add(
        Vencimiento(
            empresa_id=10, tercero_id=t.id, factura_id=None, recibo_num="R",
            iban="ES9121000418450200051332", ejercicio=2026,
            fecha_vencimiento=date(2026, 6, 1), importe=Decimal("10.0000"),
            estado=EstadoVencimiento.pendiente,
        )
    )
    await db_session.flush()
    await inactivar_tercero(db_session, 10, t.id)
    venc = await db_session.scalar(
        select(Vencimiento).where(Vencimiento.tercero_id == t.id)
    )
    assert venc is not None and t.activo is False


def test_hardening_cross_empresa_sin_fugas(terceros_client) -> None:
    client, token, _ = terceros_client
    alta = client.post(
        "/api/v1/terceros",
        json={"nif": "A12345674", "razon_social": "ACME", "es_cliente": True},
        headers=_hh(token, 10),
    )
    assert alta.status_code == 201
    tercero_id = alta.json()["id"]
    assert client.get(f"/api/v1/terceros/{tercero_id}", headers=_hh(token, 20)).status_code == 404
    assert client.delete(f"/api/v1/terceros/{tercero_id}", headers=_hh(token, 20)).status_code == 404
    resp = client.get(f"/api/v1/terceros/{tercero_id}", headers=_hh(token, 20))
    assert "ACME" not in resp.text


async def test_borrado_cross_tenant_no_afecta(db_session: AsyncSession) -> None:
    from models.iam.company import Company
    from services.acct.seed import seed_default_pgc

    for cid in (10, 20):
        db_session.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social="E SL"))
        await db_session.flush()
        await seed_default_pgc(db_session, cid)
    t = await crear_tercero(
        db_session, empresa_id=10, nif="12345678Z", razon_social="A", es_cliente=True
    )
    with pytest.raises(RetiradaError):
        await borrar_tercero(db_session, 20, t.id)
    assert await db_session.scalar(select(Tercero).where(Tercero.id == t.id)) is not None
