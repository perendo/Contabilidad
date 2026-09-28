"""Audit writer (SPEC-002 T009): insert immutable audit entry in the same ACID
transaction as the audited operation. Mirrors registrar_auditoria but exposes
root-plan naming (action/entity, actor) expected by journal flows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.audit.audit_log import AuditLog
from services.audit import registrar_auditoria


async def audit_escribir(
    session: AsyncSession,
    *,
    empresa_id: int | None,
    actor: str,
    action: str,
    entity: str,
    entity_id: int | str | None = None,
    ip: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist one immutable audit entry; payload importes serialized as str."""
    return await registrar_auditoria(
        session,
        empresa_id=empresa_id,
        operacion=action,
        entidad=entity,
        entidad_id=str(entity_id) if entity_id is not None else None,
        payload=payload,
        usuario=actor,
        ip=ip,
    )