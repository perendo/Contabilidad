"""Auditoría: persistir una entrada inmutable en la misma transacción ACID.

Paquete `services.audit`; expone `registrar_auditoria` (helper genérico) y el
módulo `services.audit.writer` (naming del plan raíz: action/entity/actor).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.audit.audit_log import AuditLog

__all__ = ["registrar_auditoria"]


async def registrar_auditoria(
    session: AsyncSession,
    empresa_id: int | None,
    operacion: str,
    entidad: str,
    entidad_id: int | str | uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    *,
    usuario: str | None = None,
    ip: str | None = None,
) -> AuditLog:
    registro = AuditLog(
        empresa_id=empresa_id,
        usuario=usuario,
        ip=ip,
        operacion=operacion,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        payload=json.dumps(payload, default=str, ensure_ascii=False) if payload else None,
    )
    session.add(registro)
    await session.flush()
    return registro
