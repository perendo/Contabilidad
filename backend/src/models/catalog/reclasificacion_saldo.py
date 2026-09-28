"""Traslado de saldos de apertura a la nueva version (SPEC-025, FR-005)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoReclasificacion(str, Enum):
    borrador = "borrador"
    contabilizado = "contabilizado"
    cuadrado = "cuadrado"


class ReclasificacionSaldo(Base):
    __tablename__ = "reclasificacion_saldo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_reclasificacion_empresa_id"),
        CheckConstraint("importe >= 0", name="chk_reclasificacion_importe_positivo"),
        ForeignKeyConstraint(
            ["empresa_id", "version_destino_id"],
            ["catalogo_version.empresa_id", "catalogo_version.id"],
            name="fk_reclasificacion_version",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "mapeo_id"],
            ["mapeo_cuenta.empresa_id", "mapeo_cuenta.id"],
            name="fk_reclasificacion_mapeo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_origen_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_reclasificacion_cuenta_origen",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_destino_id"],
            ["catalogo_cuenta.empresa_id", "catalogo_cuenta.id"],
            name="fk_reclasificacion_cuenta_destino",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_reclasificacion_asiento",
        ),
        Index("ix_reclasificacion_empresa_version", "empresa_id", "version_destino_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version_destino_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    mapeo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cuenta_origen_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cuenta_destino_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estado: Mapped[EstadoReclasificacion] = mapped_column(
        SqlEnum(EstadoReclasificacion, name="reclasificacion_estado"),
        nullable=False,
        default=EstadoReclasificacion.borrador,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
