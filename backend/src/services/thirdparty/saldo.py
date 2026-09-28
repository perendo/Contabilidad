"""Derived tercero balance and history (SPEC-008 US2 T029)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero_subcuenta import TerceroSubcuenta
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from services.reports.common import fmt


async def consultar_saldo(
    db: AsyncSession,
    empresa_id: int,
    tercero_id: uuid.UUID,
) -> dict:
    """Pending balance = Σ importe of non-settled vencimientos (Decimal)."""
    vencimientos = (
        await db.scalars(
            select(Vencimiento).where(
                Vencimiento.empresa_id == empresa_id,
                Vencimiento.tercero_id == tercero_id,
            )
        )
    ).all()
    pendientes = [
        v
        for v in vencimientos
        if v.estado in (EstadoVencimiento.pendiente, EstadoVencimiento.devuelto)
    ]
    saldo = sum((v.importe for v in pendientes), Decimal(0))
    subcuentas = (
        await db.scalars(
            select(TerceroSubcuenta).where(
                TerceroSubcuenta.empresa_id == empresa_id,
                TerceroSubcuenta.tercero_id == tercero_id,
            )
        )
    ).all()
    return {
        "saldo_pendiente": fmt(saldo),
        "n_vencimientos": len(vencimientos),
        "n_pendientes": len(pendientes),
        "subcuentas": [
            {"tipo": s.tipo.value, "cuenta_codigo": s.cuenta_codigo} for s in subcuentas
        ],
        "vencimientos": [
            {
                "id": str(v.id),
                "recibo_num": v.recibo_num,
                "fecha_vencimiento": v.fecha_vencimiento.isoformat(),
                "importe": fmt(v.importe),
                "estado": v.estado.value,
            }
            for v in vencimientos
        ],
    }
