from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.acct.journal import JournalEntry
from models.fiscal.liquidacion_retenciones import (
    EstadoLiquidacionRetenciones,
    LiquidacionRetenciones,
)
from services.fiscal.liquidacion_retenciones import (
    LiquidacionError,
    contabilizar_liquidacion,
)
from tests.conftest import sembrar_empresa_pgc


async def _crear_liquidacion(db) -> uuid.UUID:
    await sembrar_empresa_pgc(db, 1)
    liquidacion = LiquidacionRetenciones(
        empresa_id=1,
        ejercicio=2025,
        trimestre=3,
        periodo="2025-Q3",
        total_base_retenciones=Decimal("33333.3333"),
        total_retenciones=Decimal("5000.0000"),
        n_perceptores=1,
    )
    db.add(liquidacion)
    await db.flush()
    return liquidacion.id


async def test_liquidacion_duplicada_contabilizacion_rechazada(db_session):
    liquidacion_id = await _crear_liquidacion(db_session)
    await contabilizar_liquidacion(
        db_session,
        liquidacion_id=liquidacion_id,
        empresa_id=1,
        fecha_asiento=date(2025, 9, 30),
    )

    with pytest.raises(LiquidacionError) as excinfo:
        await contabilizar_liquidacion(
            db_session,
            liquidacion_id=liquidacion_id,
            empresa_id=1,
            fecha_asiento=date(2025, 10, 1),
        )

    assert excinfo.value.code == "liquidacion_ya_contabilizada"
    assert excinfo.value.status_code == 409
    entries = (
        await db_session.scalars(
            select(JournalEntry).where(JournalEntry.empresa_id == 1)
        )
    ).all()
    assert len(entries) == 1

    liquidacion = await db_session.get(LiquidacionRetenciones, liquidacion_id)
    assert liquidacion is not None
    assert liquidacion.estado == EstadoLiquidacionRetenciones.liquidado
    assert liquidacion.asiento_id == entries[0].id
