"""SolicitudReapertura (SPEC-028 T008): reapertura controlada con trazabilidad.

Research D6: la solicitud es el estado del flujo
``pendiente -> aprobada -> reabierta -> cerrada`` (o ``-> rechazada``), exige
justificacion (FR-006), permiso de rol (SPEC-015) y solo admite **una** solicitud
activa por periodo (FR-005). `numero_solicitud` es correlativo por
`(empresa_id, ejercicio)` asignado atomicamente (constitucion IV).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoPeriodoReapertura(str, Enum):
    MES = "MES"
    TRIMESTRE = "TRIMESTRE"
    ANUAL = "ANUAL"


class EstadoSolicitud(str, Enum):
    pendiente = "pendiente"
    aprobada = "aprobada"
    reabierta = "reabierta"
    cerrada = "cerrada"
    rechazada = "rechazada"


#: Estados que constituyen una solicitud activa (FR-005: una a la vez).
ESTADOS_ACTIVOS: frozenset[EstadoSolicitud] = frozenset(
    {EstadoSolicitud.pendiente, EstadoSolicitud.aprobada, EstadoSolicitud.reabierta}
)


class SolicitudReapertura(Base):
    __tablename__ = "solicitud_reapertura"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_solicitud_reapertura_empresa_id"),
        # Constitucion IV: correlatividad por (empresa, ejercicio), sin saltos.
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "numero_solicitud",
            name="uq_solicitud_reapertura_numero",
        ),
        CheckConstraint("numero_solicitud > 0", name="chk_solicitud_reapertura_numero"),
        # FR-006: la justificacion es obligatoria y no puede ser solo espacios.
        CheckConstraint("length(trim(motivo)) > 0", name="chk_solicitud_reapertura_motivo"),
        # El tipo ANUAL no puede colgar de un periodo intermedio.
        CheckConstraint(
            "(tipo_periodo = 'ANUAL' AND periodo_id IS NULL) "
            "OR (tipo_periodo <> 'ANUAL' AND periodo_id IS NOT NULL)",
            name="chk_solicitud_reapertura_periodo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "periodo_id"],
            ["periodo_cerrado.empresa_id", "periodo_cerrado.id"],
            name="fk_solicitud_reapertura_periodo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_rectificacion_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_solicitud_reapertura_asiento",
        ),
        # FR-005: una sola solicitud activa por periodo. `periodo_id` es
        # NULLABLE, asi que hacen falta dos indices parciales (NULL no colisiona
        # en un UNIQUE normal, mismo patron que SPEC-026).
        Index(
            "uq_solicitud_reapertura_activa",
            "empresa_id",
            "periodo_id",
            unique=True,
            sqlite_where=text("estado IN ('pendiente', 'aprobada', 'reabierta')"),
            postgresql_where=text("estado IN ('pendiente', 'aprobada', 'reabierta')"),
        ),
        Index("ix_solicitud_reapertura_empresa_ejercicio", "empresa_id", "ejercicio"),
        Index("ix_solicitud_reapertura_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_solicitud: Mapped[int] = mapped_column(BigInteger, nullable=False)
    periodo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    tipo_periodo: Mapped[TipoPeriodoReapertura] = mapped_column(
        SqlEnum(TipoPeriodoReapertura, name="tipo_periodo_reapertura"), nullable=False
    )
    periodo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[EstadoSolicitud] = mapped_column(
        SqlEnum(EstadoSolicitud, name="estado_solicitud_reapertura"),
        nullable=False,
        default=EstadoSolicitud.pendiente,
    )
    usuario_solicitante: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fecha_solicitud: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    aprobada_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    asiento_rectificacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    fecha_cierre_efectivo: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nota_impacto: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
