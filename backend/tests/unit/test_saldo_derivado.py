"""Tests SPEC-008 US2 (T027/T028): saldo derivado e histórico por empresa."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.iam.company import Company
from services.thirdparty.saldo import consultar_saldo


async def _empresa(db: AsyncSession, cid: int) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()


async def _tercero(db: AsyncSession, cid: int, nombre: str) -> Tercero:
    t = Tercero(empresa_id=cid, nombre=nombre, nif=None, es_cliente=True)
    db.add(t)
    await db.flush()
    return t


async def _vencimiento(
    db: AsyncSession, cid: int, tercero_id: uuid.UUID, importe: str, estado: EstadoVencimiento
) -> None:
    db.add(
        Vencimiento(
            empresa_id=cid,
            tercero_id=tercero_id,
            factura_id=None,
            recibo_num=f"R-{importe}",
            iban="ES9121000418450200051332",
            ejercicio=2026,
            fecha_vencimiento=date(2026, 6, 1),
            importe=Decimal(importe),
            estado=estado,
        )
    )
    await db.flush()


async def test_saldo_suma_vencimientos_no_liquidados(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    t = await _tercero(db_session, 10, "Cliente")
    await _vencimiento(db_session, 10, t.id, "100.0000", EstadoVencimiento.pendiente)
    await _vencimiento(db_session, 10, t.id, "50.5000", EstadoVencimiento.cobrado)
    await _vencimiento(db_session, 10, t.id, "25.2500", EstadoVencimiento.devuelto)
    saldo = await consultar_saldo(db_session, 10, t.id)
    assert saldo["saldo_pendiente"] == "125.2500"
    assert saldo["n_vencimientos"] == 3
    assert saldo["n_pendientes"] == 2


async def test_historico_solo_empresa_activa(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    t_a = await _tercero(db_session, 10, "A")
    t_b = await _tercero(db_session, 20, "B")
    await _vencimiento(db_session, 10, t_a.id, "10.0000", EstadoVencimiento.pendiente)
    await _vencimiento(db_session, 20, t_b.id, "999.0000", EstadoVencimiento.pendiente)
    saldo_a = await consultar_saldo(db_session, 10, t_a.id)
    assert saldo_a["saldo_pendiente"] == "10.0000"
    assert len(saldo_a["vencimientos"]) == 1
