"""Reusable accounting entry template header."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoPlantilla(str, Enum):
    activa = "activa"
    inactiva = "inactiva"


class PlantillaAsiento(Base):
    __tablename__ = "plantilla_asiento"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_plantilla_asiento_empresa_id"),
        UniqueConstraint("empresa_id", "nombre", name="uq_plantilla_asiento_empresa_nombre"),
        ForeignKeyConstraint(
            ["empresa_id"], ["companies.company_id"], name="fk_plantilla_asiento_empresa"
        ),
        Index("ix_plantilla_asiento_empresa", "empresa_id"),
        Index("ix_plantilla_asiento_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(50), nullable=True)
    version_actual: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    estado: Mapped[EstadoPlantilla] = mapped_column(
        SqlEnum(EstadoPlantilla, name="plantilla_estado"), nullable=False, default=EstadoPlantilla.activa
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
