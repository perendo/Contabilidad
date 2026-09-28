"""Comparativa con el ejercicio anterior (SPEC-010 T013)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from services.reporting.saldos import netos_por_cuenta, resultado_de_gestion
from services.reports.common import fmt


async def resumen_balance(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> dict | None:
    """Totales del balance del ejercicio (sin lanzar por descuadre); None si vacio."""
    netos = await netos_por_cuenta(
        db, empresa_id=empresa_id, ejercicio=ejercicio, excluir_cierre=True
    )
    if not netos:
        return None
    total_activo = Decimal(0)
    total_pasivo = Decimal(0)
    total_patrimonio = Decimal(0)
    for codigo, neto in netos.items():
        if codigo[:1] in ("6", "7"):
            continue
        if codigo[:1] == "1":
            total_patrimonio += -neto
        elif codigo[:1] in ("2", "3") or neto > 0:
            total_activo += neto
        else:
            total_pasivo += -neto
    resultado = resultado_de_gestion(netos)
    total_patrimonio += resultado
    return {
        "ejercicio": ejercicio,
        "total_activo": fmt(total_activo),
        "total_pasivo": fmt(total_pasivo),
        "total_patrimonio": fmt(total_patrimonio),
        "resultado_ejercicio": fmt(resultado),
    }