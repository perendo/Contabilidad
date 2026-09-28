"""Recargo de equivalencia (SPEC-012 T042).

La cuota de recargo (SPEC-007 FR-010) se mantiene separada del IVA general; aqui
se expone la cuota por factura con la cuenta de recargo configurada por empresa
y el estado del regimen.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.invoice.factura import Factura
from services.reports.common import fmt
from services.vat.configuracion_cuentas import (
    cuenta_recargo,
    obtener_configuracion_fiscal,
)
from services.vat.errores import error


async def aplicar_recargo(
    db: AsyncSession, *, empresa_id: int, factura_id: uuid.UUID
) -> dict:
    factura = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == factura_id
        )
    )
    if factura is None:
        raise error("factura_no_encontrada", "Factura inexistente en la empresa activa")
    cuenta = await cuenta_recargo(db, empresa_id)
    return {
        "factura_id": str(factura.id),
        "cuota_recargo": fmt(factura.importe_recargo),
        "cuenta_recargo": cuenta,
        "separado": True,
    }


async def estado_recargo(db: AsyncSession, empresa_id: int) -> dict:
    config = await obtener_configuracion_fiscal(db, empresa_id)
    return {
        "habilitado": config.recargo_equivalencia_habilitado,
        "cuenta_recargo": config.cuenta_recargo
        or (await cuenta_recargo(db, empresa_id)),
    }