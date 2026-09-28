"""Criterio de caja (SPEC-012 T043/T044): IVA diferido hasta cobro/pago.

Las facturas acogidas al regimen (``Factura.regimen_caja`` con
``iva_devengado=False``) generan un registro ``IVADiferidoCaja`` con la cuota
de IVA pendiente. Cuando el vencimiento de SPEC-011 queda saldado se liquida el
diferido (fecha de devengo real) y la factura vuelve a computar en el 303 del
periodo en que se produce el cobro/pago.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.fiscal.iva_diferido_caja import EstadoDiferido, IVADiferidoCaja
from models.invoice.factura import Factura
from services.reports.common import fmt
from services.vat.configuracion_cuentas import obtener_configuracion_fiscal
from services.vat.errores import error


async def aplicar_criterio_caja(
    db: AsyncSession, *, empresa_id: int, factura_id: uuid.UUID
) -> IVADiferidoCaja:
    factura = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == factura_id
        )
    )
    if factura is None:
        raise error("factura_no_encontrada", "Factura inexistente en la empresa activa")
    if not factura.regimen_caja:
        raise error("no_criterio_caja", "La factura no esta en regimen de caja")
    existente = await db.scalar(
        select(IVADiferidoCaja).where(
            IVADiferidoCaja.empresa_id == empresa_id,
            IVADiferidoCaja.factura_id == factura.id,
        )
    )
    if existente is not None:
        return existente
    registro = IVADiferidoCaja(
        empresa_id=empresa_id,
        factura_id=factura.id,
        cuota_diferida=factura.importe_iva,
        estado=EstadoDiferido.diferido,
    )
    db.add(registro)
    await db.flush()
    return registro


async def liquidar_diferido(
    db: AsyncSession,
    *,
    empresa_id: int,
    factura_id: uuid.UUID,
    fecha_devengo: date,
) -> IVADiferidoCaja:
    registro = await db.scalar(
        select(IVADiferidoCaja).where(
            IVADiferidoCaja.empresa_id == empresa_id,
            IVADiferidoCaja.factura_id == factura_id,
        )
    )
    if registro is None:
        raise error("diferido_no_encontrado", "No hay IVA diferido para la factura")
    registro.estado = EstadoDiferido.liquidado
    registro.fecha_devengo_real = fecha_devengo
    factura = await db.get(Factura, factura_id)
    if factura is not None:
        factura.iva_devengado = True
    await db.flush()
    return registro


async def sincronizar_con_vencimientos(
    db: AsyncSession, *, empresa_id: int
) -> dict:
    pendientes = (
        await db.scalars(
            select(IVADiferidoCaja).where(
                IVADiferidoCaja.empresa_id == empresa_id,
                IVADiferidoCaja.estado == EstadoDiferido.diferido,
            )
        )
    ).all()
    liquidados = 0
    for registro in pendientes:
        vencimiento = await db.scalar(
            select(Vencimiento).where(
                Vencimiento.empresa_id == empresa_id,
                Vencimiento.factura_id == registro.factura_id,
            )
        )
        if vencimiento is None:
            continue
        if (
            vencimiento.estado == EstadoVencimiento.cobrado
            or vencimiento.saldo_pendiente <= 0
        ):
            await liquidar_diferido(
                db,
                empresa_id=empresa_id,
                factura_id=registro.factura_id,
                fecha_devengo=vencimiento.fecha_vencimiento,
            )
            liquidados += 1
    return {"liquidados": liquidados, "pendientes": len(pendientes) - liquidados}


async def estado_criterio_caja(db: AsyncSession, empresa_id: int) -> dict:
    config = await obtener_configuracion_fiscal(db, empresa_id)
    filas = (
        await db.scalars(
            select(IVADiferidoCaja.cuota_diferida).where(
                IVADiferidoCaja.empresa_id == empresa_id,
                IVADiferidoCaja.estado == EstadoDiferido.diferido,
            )
        )
    ).all()
    total = sum(filas, Decimal(0))
    return {
        "habilitado": config.criterio_caja_habilitado,
        "diferidos_pendientes": fmt(total),
    }