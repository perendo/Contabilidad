"""Immutable access-audit writer (FR-005).

Events are written inside the request ACID boundary. For denials the caller
commits (the 403 aborts the rest of the transaction); for grants the caller
flushes so the event commits atomically with the business operation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.rbac.evento_auditoria_acceso import (
    EventoAuditoriaAcceso,
    MotivoAcceso,
    ResultadoAcceso,
)


async def registrar(
    db: AsyncSession,
    *,
    empresa_id: int,
    usuario_id: int,
    rol_id: object | None,
    modulo: str,
    operacion: str,
    resultado: ResultadoAcceso,
    motivo: MotivoAcceso,
    ip: str | None = None,
    payload: dict | None = None,
    commit: bool = False,
) -> EventoAuditoriaAcceso:
    evento = EventoAuditoriaAcceso(
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        rol_id=rol_id,
        modulo=modulo,
        operacion=operacion,
        resultado=resultado,
        motivo=motivo,
        ip=ip,
        payload=payload,
    )
    db.add(evento)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return evento


async def listar_eventos(
    db: AsyncSession,
    *,
    empresa_id: int,
    resultado: ResultadoAcceso | None = None,
    modulo: str | None = None,
    operacion: str | None = None,
    usuario_id: int | None = None,
    fecha_gte: datetime | None = None,
    fecha_lte: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    filtros = [EventoAuditoriaAcceso.empresa_id == empresa_id]
    if resultado is not None:
        filtros.append(EventoAuditoriaAcceso.resultado == resultado)
    if modulo is not None:
        filtros.append(EventoAuditoriaAcceso.modulo == modulo)
    if operacion is not None:
        filtros.append(EventoAuditoriaAcceso.operacion == operacion)
    if usuario_id is not None:
        filtros.append(EventoAuditoriaAcceso.usuario_id == usuario_id)
    if fecha_gte is not None:
        filtros.append(EventoAuditoriaAcceso.timestamp_utc >= fecha_gte)
    if fecha_lte is not None:
        filtros.append(EventoAuditoriaAcceso.timestamp_utc <= fecha_lte)

    total = (
        await db.scalar(
            select(func.count()).select_from(EventoAuditoriaAcceso).where(*filtros)
        )
    ) or 0
    filas = (
        await db.scalars(
            select(EventoAuditoriaAcceso)
            .where(*filtros)
            .order_by(EventoAuditoriaAcceso.timestamp_utc.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        {
            "evento_id": str(f.id),
            "usuario_id": int(f.usuario_id),
            "rol_id": str(f.rol_id) if f.rol_id is not None else None,
            "modulo": f.modulo,
            "operacion": f.operacion,
            "resultado": f.resultado.value,
            "motivo": f.motivo.value,
            "timestamp_utc": f.timestamp_utc.isoformat(),
            "ip": f.ip,
        }
        for f in filas
    ]
    return items, total