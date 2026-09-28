"""Tests SPEC-008 Polish (T043): condiciones de pronto pago (T-08/FR-009).

Desviación: el CRUD vive en `services/tercero_amend.py` (SPEC-020) y, al
crear una condición vigente, desactiva la anterior en vez de devolver 409
(una única vigente por tercero). Se prueba el comportamiento real.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.treasury.condicion_pronto_pago import CondicionProntoPago
from services.tercero_amend import (
    TerceroAmendError,
    actualizar_condicion,
    crear_condicion,
)


async def _empresa(db: AsyncSession, cid: int = 10) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()


async def test_crear_vigente_desactiva_previa(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    tercero = uuid.uuid4()
    await crear_condicion(db_session, 10, tercero, 10, Decimal("2.00"))
    await crear_condicion(db_session, 10, tercero, 15, Decimal("1.50"))
    vigentes = await db_session.scalar(
        select(func.count(CondicionProntoPago.id)).where(
            CondicionProntoPago.empresa_id == 10,
            CondicionProntoPago.tercero_id == tercero,
            CondicionProntoPago.vigente.is_(True),
        )
    )
    assert vigentes == 1


async def test_validaciones_plazo_y_porcentaje(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    tercero = uuid.uuid4()
    with pytest.raises(TerceroAmendError):
        await crear_condicion(db_session, 10, tercero, 0, Decimal("2.00"))
    with pytest.raises(TerceroAmendError):
        await crear_condicion(db_session, 10, tercero, 10, Decimal(0))


async def test_desactivar_y_aislamiento_empresa(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    await _empresa(db_session, 20)
    tercero = uuid.uuid4()
    condicion = await crear_condicion(db_session, 10, tercero, 10, Decimal("2.00"))
    desactivada = await actualizar_condicion(db_session, 10, condicion.id, vigente=False)
    assert desactivada.vigente is False
    with pytest.raises(TerceroAmendError):
        await actualizar_condicion(db_session, 20, condicion.id, vigente=True)
