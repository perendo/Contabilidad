"""Immutable access-audit event (FR-005, constitution II applied to audit).

Records every denied attempt and every granted permission that touches
accounting data, in the same ACID transaction as the operation or its denial
(trigger-enforced immutability: no UPDATE/DELETE).

`operacion` is stored as String instead of the catalog enum so arbitrary
attempted operations (unknown to the closed catalog) can still be audited
without crashing the insert.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ResultadoAcceso(str, enum.Enum):
    allow = "allow"
    deny = "deny"


class MotivoAcceso(str, enum.Enum):
    sin_permiso = "sin_permiso"
    sin_rol = "sin_rol"
    operacion_inexistente = "operacion_inexistente"
    sin_empresa = "sin_empresa"
    concedido = "concedido"


class EventoAuditoriaAcceso(Base):
    __tablename__ = "evento_auditoria_acceso"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_evento_acceso_tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", name="fk_evento_acceso_usuario"),
        nullable=False,
        index=True,
    )
    rol_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("roles.id", name="fk_evento_acceso_rol"),
        nullable=True,
        index=True,
    )
    modulo: Mapped[str] = mapped_column(String(40), nullable=False)
    operacion: Mapped[str] = mapped_column(String(40), nullable=False)
    resultado: Mapped[ResultadoAcceso] = mapped_column(
        SqlEnum(ResultadoAcceso, name="resultado_acceso"), nullable=False
    )
    motivo: Mapped[MotivoAcceso] = mapped_column(
        SqlEnum(MotivoAcceso, name="motivo_acceso"), nullable=False
    )
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)