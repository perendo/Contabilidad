"""Informe de antigüedad de saldos por tercero (SPEC-011 US3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from services.reports.common import fmt

RANGOS = (("rango_30", 30), ("rango_60", 60), ("rango_90", 90), ("rango_90mas", None))


def _rango(dias: int) -> str:
    if dias <= 30:
        return "rango_30"
    if dias <= 60:
        return "rango_60"
    if dias <= 90:
        return "rango_90"
    return "rango_90mas"


async def calcular_antiguedad(
    db: AsyncSession, *, empresa_id: int, fecha_corte: date
) -> dict:
    """Pending balances per tercero and aging bucket; buckets sum the total."""
    vencimientos = (
        await db.scalars(
            select(Vencimiento).where(
                Vencimiento.empresa_id == empresa_id,
                Vencimiento.estado.in_(
                    (EstadoVencimiento.pendiente, EstadoVencimiento.parcial)
                ),
            )
        )
    ).all()
    nombres = {
        t.id: t.nombre
        for t in (
            await db.scalars(select(Tercero).where(Tercero.empresa_id == empresa_id))
        ).all()
    }
    por_tercero: dict = {}
    total = Decimal(0)
    for v in vencimientos:
        dias = (fecha_corte - v.fecha_vencimiento).days
        bucket = _rango(max(dias, 0))
        saldo = v.saldo_pendiente
        total += saldo
        fila = por_tercero.setdefault(
            str(v.tercero_id),
            {
                "tercero_id": str(v.tercero_id),
                "nombre": nombres.get(v.tercero_id, ""),
                **{r: Decimal(0) for r, _ in RANGOS},
                "total": Decimal(0),
            },
        )
        fila[bucket] += saldo
        fila["total"] += saldo
    items = [
        {**{k: (fmt(v) if isinstance(v, Decimal) else v) for k, v in fila.items()}}
        for fila in por_tercero.values()
    ]
    suma_rangos = sum(
        (Decimal(fila["total"]) for fila in items), Decimal(0)
    )
    assert suma_rangos == total
    return {"fecha_corte": fecha_corte.isoformat(), "total": fmt(total), "items": items}
