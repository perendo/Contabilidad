"""Variables resolved when generating an entry from a template."""

from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoVariable(str, Enum):
    importe = "importe"


class VariablePlantilla(Base):
    __tablename__ = "variable_plantilla"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_variable_plantilla_empresa_id"),
        ForeignKeyConstraint(
            ["empresa_id", "plantilla_id"],
            ["plantilla_asiento.empresa_id", "plantilla_asiento.id"],
            name="fk_variable_plantilla_empresa_plantilla",
        ),
        Index("ix_variable_plantilla_empresa", "empresa_id"),
        Index("ix_variable_plantilla_empresa_plantilla", "empresa_id", "plantilla_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    plantilla_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo: Mapped[TipoVariable] = mapped_column(
        SqlEnum(TipoVariable, name="plantilla_variable_tipo"), nullable=False, default=TipoVariable.importe
    )
    es_requerida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
