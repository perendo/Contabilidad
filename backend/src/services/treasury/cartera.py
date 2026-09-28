"""Consulta de la cartera de efectos (SPEC-021 US3).

Listado paginado con filtros (estado, tipo, tercero, rango de vencimiento),
agrupación por estado/tipo con importes agregados en Decimal y detalle de
un efecto con su tercero y los asientos de cobro/impago asociados.
Siempre filtrado por la empresa activa de sesión (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry
from models.ar.tercero import Tercero
from models.treasury.efecto import Efecto, EstadoEfecto, TipoEfecto


def _out(efecto: Efecto, tercero_nombre: str | None) -> dict:
    return {
        "id": str(efecto.id),
        "tercero_id": str(efecto.tercero_id),
        "tercero_nombre": tercero_nombre,
        "tipo_efecto": efecto.tipo_efecto.value,
        "numero_documento": efecto.numero_documento,
        "fecha_emision": efecto.fecha_emision.isoformat(),
        "fecha_vencimiento": efecto.fecha_vencimiento.isoformat(),
        "importe": f"{efecto.importe:0.4f}",
        "moneda": efecto.moneda,
        "estado": efecto.estado.value,
        "asiento_cobro_id": str(efecto.asiento_cobro_id) if efecto.asiento_cobro_id else None,
        "asiento_impago_id": str(efecto.asiento_impago_id) if efecto.asiento_impago_id else None,
        "notas": efecto.notas,
    }


def _filtros(
    empresa_id: int,
    *,
    estado: EstadoEfecto | None,
    tipo_efecto: TipoEfecto | None,
    tercero_id: uuid.UUID | None,
    fecha_desde: date | None,
    fecha_hasta: date | None,
) -> list:
    condiciones = [Efecto.empresa_id == empresa_id]
    if estado is not None:
        condiciones.append(Efecto.estado == estado)
    if tipo_efecto is not None:
        condiciones.append(Efecto.tipo_efecto == tipo_efecto)
    if tercero_id is not None:
        condiciones.append(Efecto.tercero_id == tercero_id)
    if fecha_desde is not None:
        condiciones.append(Efecto.fecha_vencimiento >= fecha_desde)
    if fecha_hasta is not None:
        condiciones.append(Efecto.fecha_vencimiento <= fecha_hasta)
    return condiciones


async def consultar_cartera(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: EstadoEfecto | None = None,
    tipo_efecto: TipoEfecto | None = None,
    tercero_id: uuid.UUID | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    condiciones = _filtros(
        empresa_id,
        estado=estado,
        tipo_efecto=tipo_efecto,
        tercero_id=tercero_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    total = await db.scalar(select(func.count(Efecto.id)).where(*condiciones))
    filas = (
        await db.execute(
            select(Efecto, Tercero.nombre)
            .outerjoin(
                Tercero,
                (Tercero.empresa_id == Efecto.empresa_id)
                & (Tercero.id == Efecto.tercero_id),
            )
            .where(*condiciones)
            .order_by(Efecto.fecha_vencimiento, Efecto.numero_documento)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items = [_out(efecto, nombre) for efecto, nombre in filas]
    return items, total or 0


async def agrupar_cartera(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: EstadoEfecto | None = None,
    tipo_efecto: TipoEfecto | None = None,
    tercero_id: uuid.UUID | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict:
    condiciones = _filtros(
        empresa_id,
        estado=estado,
        tipo_efecto=tipo_efecto,
        tercero_id=tercero_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    por_estado = (
        await db.execute(
            select(
                Efecto.estado,
                func.count(Efecto.id),
                func.coalesce(func.sum(Efecto.importe), 0),
            )
            .where(*condiciones)
            .group_by(Efecto.estado)
        )
    ).all()
    por_tipo = (
        await db.execute(
            select(
                Efecto.tipo_efecto,
                func.count(Efecto.id),
                func.coalesce(func.sum(Efecto.importe), 0),
            )
            .where(*condiciones)
            .group_by(Efecto.tipo_efecto)
        )
    ).all()
    return {
        "por_estado": [
            {"estado": estado.value, "total": total, "importe": f"{importe:0.4f}"}
            for estado, total, importe in por_estado
        ],
        "por_tipo": [
            {"tipo_efecto": tipo.value, "total": total, "importe": f"{importe:0.4f}"}
            for tipo, total, importe in por_tipo
        ],
    }


async def detalle_efecto(
    db: AsyncSession,
    *,
    empresa_id: int,
    efecto_id: uuid.UUID,
) -> dict | None:
    fila = (
        await db.execute(
            select(Efecto, Tercero.nombre)
            .outerjoin(
                Tercero,
                (Tercero.empresa_id == Efecto.empresa_id)
                & (Tercero.id == Efecto.tercero_id),
            )
            .where(Efecto.empresa_id == empresa_id, Efecto.id == efecto_id)
        )
    ).first()
    if fila is None:
        return None
    efecto, tercero_nombre = fila
    datos = _out(efecto, tercero_nombre)
    asientos: dict = {}
    asientos_ids = {
        "asiento_cobro_id": efecto.asiento_cobro_id,
        "asiento_impago_id": efecto.asiento_impago_id,
    }
    for campo, asiento_id in asientos_ids.items():
        if asiento_id is None:
            continue
        asiento = await db.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == empresa_id, JournalEntry.id == asiento_id
            )
        )
        if asiento is not None:
            asientos[campo] = {
                "id": str(asiento.id),
                "fecha": asiento.fecha.isoformat(),
                "tipo": asiento.tipo.value,
                "concepto": asiento.concepto,
                "numero_asiento": asiento.numero_asiento,
            }
    datos["asientos"] = asientos
    return datos