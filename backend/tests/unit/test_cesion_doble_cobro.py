"""Test impedir doble cobro de vencimiento cedido (SPEC-022 T032, US3).

FR-005: un vencimiento cedido no puede cobrarse por los canales normales ni
cederse de nuevo.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.treasury.cesion import TipoComisionCesion
from services.treasury.cesion import CesionError, registrar_cesion
from services.treasury.cobros_pagos import CobroPagoError, registrar_cobro
from tests.unit.anticipo_support import sembrar_base


async def test_cobrar_vencimiento_cedido_rechazado(db_session):
    base = await sembrar_base(db_session, 1, n_vencimientos=1)
    vid = base["vencimientos"][0]

    await registrar_cesion(
        db_session,
        empresa_id=1,
        entidad_financiera="Banco X",
        fecha_cesion=date(2026, 7, 1),
        vencimiento_ids=[vid],
        comision="0.0000",
        tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
    )
    await db_session.flush()

    with pytest.raises(CobroPagoError) as excinfo:
        await registrar_cobro(
            db_session, empresa_id=1, vencimiento_id=vid, fecha=date(2026, 8, 1),
            importe="1500.0000",
        )
    assert excinfo.value.code == "vencimiento_cedido"


async def test_ceder_vencimiento_ya_cedido_rechazado(db_session):
    base = await sembrar_base(db_session, 1, n_vencimientos=2)
    v1, v2 = base["vencimientos"]

    await registrar_cesion(
        db_session,
        empresa_id=1,
        entidad_financiera="Banco X",
        fecha_cesion=date(2026, 7, 1),
        vencimiento_ids=[v1],
        comision="0.0000",
        tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
    )
    await db_session.flush()

    with pytest.raises(CesionError) as excinfo:
        await registrar_cesion(
            db_session,
            empresa_id=1,
            entidad_financiera="Banco Z",
            fecha_cesion=date(2026, 7, 2),
            vencimiento_ids=[v1, v2],
            comision="10.0000",
            tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
        )
    assert excinfo.value.code == "vencimiento_no_pendiente"
    assert excinfo.value.status_code == 409