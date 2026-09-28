"""Immutable audit log scaffold (constitution: audit in same ACID transaction).

`empresa_id` is nullable because authentication events (LOGIN_FAILED) happen
before any company context exists. `entity_id` is stored as string so both UUID
(treasury) and BIGINT (account_plan, journals) identifiers can be traced.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (UniqueConstraint("empresa_id", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    usuario: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    operacion: Mapped[str] = mapped_column(String(64), nullable=False)
    entidad: Mapped[str] = mapped_column(String(64), nullable=False)
    entidad_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )