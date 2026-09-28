"""NotificacionCesion model (SPEC-022 US3): registro de la comunicación.

La cesión de cobros exige notificar al cliente deudor (requisito legal del
factoring). Este modelo guarda la traza de la notificación: fecha, medio
(email/correo/registro) y estado. No genera asiento (informativa, research
D5) y es trazable para auditoría. Multi-tenant estricto (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class MedioNotificacion(str, Enum):
    EMAIL = "EMAIL"
    CORREO = "CORREO"
    REGISTRO = "REGISTRO"


class EstadoNotificacion(str, Enum):
    pendiente = "pendiente"
    enviada = "enviada"


class NotificacionCesion(Base):
    __tablename__ = "notificacion_cesion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_notificacion_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id", "cesion_id"],
            ["cesion_cobro.empresa_id", "cesion_cobro.id"],
            name="fk_notificacion_cesion",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cliente_id"],
            ["tercero.empresa_id", "tercero.id"],
            name="fk_notificacion_cliente",
        ),
        Index(
            "ix_notificacion_empresa_cesion", "empresa_id", "cesion_id"
        ),
        Index("ix_notificacion_empresa_cliente", "empresa_id", "cliente_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cesion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    cliente_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    fecha_notificacion: Mapped[date] = mapped_column(Date, nullable=False)
    medio: Mapped[MedioNotificacion] = mapped_column(
        SqlEnum(MedioNotificacion, name="medio_notificacion_cesion"), nullable=False
    )
    estado: Mapped[EstadoNotificacion] = mapped_column(
        SqlEnum(EstadoNotificacion, name="estado_notificacion_cesion"),
        nullable=False,
        default=EstadoNotificacion.enviada,
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )