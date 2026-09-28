"""Test cesión solo sobre vencimientos pendientes (SPEC-022 T033, US3).

Ceder un vencimiento ya cobrado → 409 ``vencimiento_no_pendiente``; ceder una
lista vacía → 422 ``sin_vencimientos``.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.cesion import TipoComisionCesion
from services.treasury.cesion import CesionError, registrar_cesion
from tests.unit.anticipo_support import sembrar_base


async def test_cesion_con_vencimiento_cobrado_rechazado(db_session):
    base = await sembrar_base(db_session, 1, n_vencimientos=2)
    v1, v2 = base["vencimientos"]

    cobrado = await db_session.scalar(select(Vencimiento).where(Vencimiento.id == v1))
    cobrado.estado = EstadoVencimiento.cobrado
    await db_session.flush()

    with pytest.raises(CesionError) as excinfo:
        await registrar_cesion(
            db_session,
            empresa_id=1,
            entidad_financiera="Banco X",
            fecha_cesion=date(2026, 7, 1),
            vencimiento_ids=[v1, v2],
            comision="0.0000",
            tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
        )
    assert excinfo.value.code == "vencimiento_no_pendiente"
    assert excinfo.value.status_code == 409


async def test_cesion_vacia_rechazada(db_session):
    await sembrar_base(db_session, 1)
    with pytest.raises(CesionError) as excinfo:
        await registrar_cesion(
            db_session,
            empresa_id=1,
            entidad_financiera="Banco X",
            fecha_cesion=date(2026, 7, 1),
            vencimiento_ids=[],
            comision="0.0000",
            tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
        )
    assert excinfo.value.code == "sin_vencimientos"
    assert excinfo.value.status_code == 422