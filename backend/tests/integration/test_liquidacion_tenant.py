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


async def _crear_liquidacion(session, empresa_id: int, trimestre: int) -> str:
    liquidacion = LiquidacionRetenciones(
        empresa_id=empresa_id,
        ejercicio=2025,
        trimestre=trimestre,
        periodo=f"2025-Q{trimestre}",
        total_base_retenciones=Decimal("1000.0000"),
        total_retenciones=Decimal("150.0000"),
        n_perceptores=1,
    )
    session.add(liquidacion)
    await session.flush()
    return str(liquidacion.id)


def test_liquidacion_de_otra_empresa_devuelve_404(retenciones_client):
    api = retenciones_client
    liquidacion_id = api.run(api.mutar(lambda session: _crear_liquidacion(session, 10, 3)))

    with pytest.raises(LiquidacionError) as excinfo:
        api.run(
            api.mutar(
                lambda session: contabilizar_liquidacion(
                    session,
                    liquidacion_id=uuid.UUID(liquidacion_id),
                    empresa_id=20,
                    fecha_asiento=date(2025, 9, 30),
                )
            )
        )

    assert excinfo.value.code == "liquidacion_no_encontrada"
    assert excinfo.value.status_code == 404

    async def _estado(session):
        liquidacion = await session.scalar(
            select(LiquidacionRetenciones).where(
                LiquidacionRetenciones.empresa_id == 10,
                LiquidacionRetenciones.id == uuid.UUID(liquidacion_id),
            )
        )
        count = len(
            (
                await session.scalars(
                    select(JournalEntry).where(JournalEntry.empresa_id == 20)
                )
            ).all()
        )
        return liquidacion, count

    liquidacion, count_b = api.run(api.consultar(_estado))
    assert liquidacion is not None
    assert liquidacion.estado == EstadoLiquidacionRetenciones.pendiente
    assert liquidacion.asiento_id is None
    assert count_b == 0
