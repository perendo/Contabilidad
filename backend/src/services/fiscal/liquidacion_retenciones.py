"""Liquidación contable de retenciones IRPF con asiento 4751/572."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.fiscal.liquidacion_retenciones import (
    EstadoLiquidacionRetenciones,
    LiquidacionRetenciones,
)
from services.audit import registrar_auditoria
from services.fiscal.errores import FiscalISError
from services.journal.motor import crear_asiento_multilinea
from services.journal.validador_multilinea import MultilineaError

CUENTA_RETENCIONES = "4751"
CUENTA_BANCO_POR_DEFECTO = "5720"


class LiquidacionError(FiscalISError):
    """Error de dominio con código HTTP para la liquidación."""

    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(code, message)
        self.status_code = status_code


async def _validar_cuenta_apuntable(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo: str,
    prefijo_error: str,
) -> None:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == codigo,
        )
    )
    if cuenta is None:
        raise LiquidacionError(
            f"{prefijo_error}_no_encontrada",
            422,
            f"La cuenta {codigo} no existe en la empresa activa",
        )
    if not cuenta.is_selectable or not cuenta.is_active:
        raise LiquidacionError(
            f"{prefijo_error}_no_apuntable",
            422,
            f"La cuenta {codigo} no es apuntable en la empresa activa",
        )


async def contabilizar_liquidacion(
    db: AsyncSession,
    *,
    liquidacion_id: uuid.UUID,
    empresa_id: int,
    fecha_asiento: date,
    cuenta_banco: str = CUENTA_BANCO_POR_DEFECTO,
    actor: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    """Contabiliza 4751 contra 572 y marca la liquidación como final."""
    liquidacion = await db.scalar(
        select(LiquidacionRetenciones)
        .where(
            LiquidacionRetenciones.empresa_id == empresa_id,
            LiquidacionRetenciones.id == liquidacion_id,
        )
        .with_for_update()
    )
    if liquidacion is None:
        raise LiquidacionError(
            "liquidacion_no_encontrada", 404, "La liquidación no existe en la empresa activa"
        )
    if liquidacion.estado != EstadoLiquidacionRetenciones.pendiente:
        raise LiquidacionError(
            "liquidacion_ya_contabilizada",
            409,
            "La liquidación ya está contabilizada",
        )

    total = liquidacion.total_retenciones
    if not total.is_finite() or total <= 0:
        raise LiquidacionError(
            "sin_retenciones", 422, "La liquidación no tiene retenciones para contabilizar"
        )

    cuenta_banco = cuenta_banco.strip()
    await _validar_cuenta_apuntable(
        db,
        empresa_id=empresa_id,
        codigo=CUENTA_RETENCIONES,
        prefijo_error="cuenta_retenciones",
    )
    await _validar_cuenta_apuntable(
        db,
        empresa_id=empresa_id,
        codigo=cuenta_banco,
        prefijo_error="cuenta_banco",
    )

    try:
        asiento = await crear_asiento_multilinea(
            db,
            empresa_id=empresa_id,
            fecha=fecha_asiento,
            concepto=(
                f"Liquidación retenciones {liquidacion.periodo} "
                f"[{liquidacion.id}]"
            ),
            lineas=[
                {
                    "cuenta": CUENTA_RETENCIONES,
                    "debe": total,
                    "haber": Decimal("0.0000"),
                    "detalle": f"Retenciones {liquidacion.periodo}",
                },
                {
                    "cuenta": cuenta_banco,
                    "debe": Decimal("0.0000"),
                    "haber": total,
                    "detalle": f"Ingreso retenciones {liquidacion.periodo}",
                },
            ],
            actor=actor,
        )
    except MultilineaError as exc:
        raise LiquidacionError(exc.code, 422, str(exc)) from exc

    liquidacion.estado = EstadoLiquidacionRetenciones.liquidado
    liquidacion.fecha_liquidacion = fecha_asiento
    liquidacion.asiento_id = asiento.id
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="CONTABILIZAR_LIQUIDACION",
        entidad="liquidacion_retenciones",
        entidad_id=liquidacion.id,
        payload={
            "liquidacion_id": str(liquidacion.id),
            "periodo": liquidacion.periodo,
            "fecha_asiento": fecha_asiento.isoformat(),
            "asiento_id": str(asiento.id),
            "cuenta_banco": cuenta_banco,
            "total_retenciones": f"{total:0.4f}",
        },
        ip=ip,
    )
    await db.flush()
    return {
        "asiento_id": asiento.id,
        "estado": EstadoLiquidacionRetenciones.liquidado,
        "fecha_liquidacion": fecha_asiento,
        "total_retenciones": total,
    }


__all__ = [
    "CUENTA_BANCO_POR_DEFECTO",
    "CUENTA_RETENCIONES",
    "LiquidacionError",
    "contabilizar_liquidacion",
]
