from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.acct.journal import JournalEntry
from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from services.fiscal.liquidacion_retenciones import (
    LiquidacionError,
    contabilizar_liquidacion,
)
from tests.conftest import sembrar_empresa_pgc


async def _crear_liquidacion(db, total: Decimal) -> uuid.UUID:
    await sembrar_empresa_pgc(db, 1)
    liquidacion = LiquidacionRetenciones(
        empresa_id=1,
        ejercicio=2025,
        trimestre=3,
        periodo="2025-Q3",
        total_base_retenciones=Decimal("0.0000"),
        total_retenciones=total,
        n_perceptores=0,
    )
    db.add(liquidacion)
    await db.flush()
    return liquidacion.id


async def test_liquidacion_sin_retenciones_rechazada(db_session):
    liquidacion_id = await _crear_liquidacion(db_session, Decimal("0.0000"))

    with pytest.raises(LiquidacionError) as excinfo:
        await contabilizar_liquidacion(
            db_session,
            liquidacion_id=liquidacion_id,
            empresa_id=1,
            fecha_asiento=date(2025, 9, 30),
        )

    assert excinfo.value.code == "sin_retenciones"
    assert excinfo.value.status_code == 422
    entries = (
        await db_session.scalars(
            select(JournalEntry).where(JournalEntry.empresa_id == 1)
        )
    ).all()
    assert entries == []
