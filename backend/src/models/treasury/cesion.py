"""CesionCobro model (SPEC-022 US3): factoring/confirming sobre vencimientos.

Una cesión transfiere el derecho de cobro de unos vencimientos ``pendientes``
a una entidad financiera. Se registra con su comisión (importe fijo o
porcentaje), el total cedido y el neto recibido, y genera el asiento
Debe 572 (neto) + 662 (comisión) | Haber 430 (total). Los vencimientos pasan a
estado ``cedido`` y no pueden cobrarse de nuevo (FR-005).

Multi-tenant estricto (constitución III): ``empresa_id`` en claves, FKs
compuestas e índices. Importes ``NUMERIC(18,4)``/``Decimal``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
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


class TipoComisionCesion(str, Enum):
    IMPORTE_FIJO = "IMPORTE_FIJO"
    PORCENTAJE = "PORCENTAJE"


class EstadoCesion(str, Enum):
    activa = "activa"
    saldada = "saldada"
    cancelada = "cancelada"


class CesionCobro(Base):
    __tablename__ = "cesion_cobro"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_cesion_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_cesion_asiento",
        ),
        CheckConstraint(
            "comision >= 0", name="chk_cesion_comision_no_negativa"
        ),
        CheckConstraint(
            "importe_total_cedido > 0", name="chk_cesion_total_positivo"
        ),
        CheckConstraint(
            "importe_neto_recibido >= 0", name="chk_cesion_neto_no_negativo"
        ),
        Index("ix_cesion_empresa_fecha", "empresa_id", "fecha_cesion"),
        Index("ix_cesion_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    entidad_financiera: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_cesion: Mapped[date] = mapped_column(Date, nullable=False)
    comision: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    tipo_comision: Mapped[TipoComisionCesion] = mapped_column(
        SqlEnum(TipoComisionCesion, name="tipo_comision_cesion"), nullable=False
    )
    importe_total_cedido: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    importe_neto_recibido: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    estado: Mapped[EstadoCesion] = mapped_column(
        SqlEnum(EstadoCesion, name="cesion_estado"),
        nullable=False,
        default=EstadoCesion.activa,
    )
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CesionCobroDetalle(Base):
    __tablename__ = "cesion_cobro_detalle"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_cesion_detalle_tenant_id"),
        UniqueConstraint(
            "empresa_id", "cesion_id", "vencimiento_id", name="uq_cesion_vencimiento"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cesion_id"],
            ["cesion_cobro.empresa_id", "cesion_cobro.id"],
            name="fk_cesion_detalle_cesion",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "vencimiento_id"],
            ["vencimiento.empresa_id", "vencimiento.id"],
            name="fk_cesion_detalle_vencimiento",
        ),
        CheckConstraint("importe > 0", name="chk_cesion_detalle_importe_positivo"),
        Index("ix_cesion_detalle_empresa_cesion", "empresa_id", "cesion_id"),
        Index("ix_cesion_detalle_empresa_vencimiento", "empresa_id", "vencimiento_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cesion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    vencimiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)