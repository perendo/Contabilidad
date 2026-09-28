"""Template lines with mutually exclusive fixed and variable amounts."""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class PosicionLinea(str, Enum):
    debe = "debe"
    haber = "haber"


class LineaPlantilla(Base):
    __tablename__ = "linea_plantilla"
    __table_args__ = (
        CheckConstraint(
            "(importe_fijo IS NOT NULL AND variable_id IS NULL) OR (importe_fijo IS NULL AND variable_id IS NOT NULL)",
            name="linea_plantilla_fijo_variable_excluyentes",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "plantilla_id"],
            ["plantilla_asiento.empresa_id", "plantilla_asiento.id"],
            name="fk_linea_plantilla_empresa_plantilla",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "variable_id"],
            ["variable_plantilla.empresa_id", "variable_plantilla.id"],
            name="fk_linea_plantilla_empresa_variable",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_linea_plantilla_empresa_cuenta",
        ),
        Index("ix_linea_plantilla_empresa", "empresa_id"),
        Index("ix_linea_plantilla_empresa_plantilla", "empresa_id", "plantilla_id", "orden"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    plantilla_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    posicion: Mapped[PosicionLinea] = mapped_column(SqlEnum(PosicionLinea, name="plantilla_posicion"), nullable=False)
    importe_fijo: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    variable_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
