"""Receivable exclusion tests (T015).

FR-003/FR-008: receivables that are collected, lack IBAN, belong to a closed
exercise or do not exist are excluded; a closed exercise raises a hard error.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.remesa import Remesa
from services.remittance.emision import InelegibleError, crear_remesa
from services.remittance.seleccion import EjercicioCerradoError


async def _vencimiento(
    session: AsyncSession,
    *,
    estado: EstadoVencimiento = EstadoVencimiento.pendiente,
    iban: str = "ES9121000418450200051332",
    ejercicio: int = 2026,
    importe: str = "150.0000",
) -> Vencimiento:
    vencimiento = Vencimiento(
        empresa_id=7,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num=f"R-{uuid.uuid4().hex[:8]}",
        iban=iban,
        ejercicio=ejercicio,
        fecha_vencimiento=date(2026, 10, 10),
        importe=Decimal(importe),
        estado=estado,
    )
    session.add(vencimiento)
    await session.flush()
    return vencimiento


async def test_recibo_cobrado_excluido_y_lista_devuelta(db_session):
    cobrado = await _vencimiento(
        db_session, estado=EstadoVencimiento.cobrado
    )
    valido = await _vencimiento(db_session)

    with pytest.raises(InelegibleError) as exc:
        await crear_remesa(
            db_session,
            7,
            formato="SEPA_DD",
            tipo_adeudo="CORE",
            vencimiento_ids=[cobrado.id, valido.id],
        )
    motivos = {x.vencimiento_id: x.motivo for x in exc.value.excluidos}
    assert cobrado.id in motivos
    assert motivos[cobrado.id] == "ya_cobrado"
    assert len(motivos) == 1


async def test_sin_iban_excluido(db_session):
    sin_iban = await _vencimiento(db_session, iban="ES123")
    with pytest.raises(InelegibleError) as exc:
        await crear_remesa(
            db_session,
            7,
            formato="SEPA_DD",
            tipo_adeudo="CORE",
            vencimiento_ids=[sin_iban.id],
        )
    motivos = {x.vencimiento_id: x.motivo for x in exc.value.excluidos}
    assert motivos[sin_iban.id] == "sin_iban"


async def test_vencimiento_inexistente_excluido(db_session):
    inexistente = uuid.uuid4()
    with pytest.raises(InelegibleError) as exc:
        await crear_remesa(
            db_session,
            7,
            formato="SEPA_DD",
            tipo_adeudo="CORE",
            vencimiento_ids=[inexistente],
        )
    motivos = {x.vencimiento_id: x.motivo for x in exc.value.excluidos}
    assert motivos[inexistente] == "no_encontrado"


async def test_ejercicio_cerrado_rechazado(db_session):
    cerrado = await _vencimiento(db_session, ejercicio=2024)
    with pytest.raises(EjercicioCerradoError):
        await crear_remesa(
            db_session,
            7,
            formato="SEPA_DD",
            tipo_adeudo="CORE",
            vencimiento_ids=[cerrado.id],
        )


async def test_fallo_atomico_no_crea_remesa(db_session):
    valido = await _vencimiento(db_session)
    cobrado = await _vencimiento(
        db_session, estado=EstadoVencimiento.cobrado
    )
    with pytest.raises(InelegibleError):
        await crear_remesa(
            db_session,
            7,
            formato="SEPA_DD",
            tipo_adeudo="CORE",
            vencimiento_ids=[valido.id, cobrado.id],
        )
    total = await db_session.scalar(
        select(func.count()).select_from(Remesa).where(Remesa.empresa_id == 7)
    )
    assert total == 0


async def test_todos_elegibles_se_incluyen(db_session):
    v1 = await _vencimiento(db_session, importe="200.0000")
    v2 = await _vencimiento(db_session, importe="100.0000")
    remesa = await crear_remesa(
        db_session,
        7,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[v1.id, v2.id],
    )
    assert remesa.importe_total == Decimal("300.0000")
    assert remesa.numero_remesa == 1