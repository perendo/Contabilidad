"""CondicionProntoPago model: condiciones de pronto pago por tercero (SPEC-008)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class CondicionProntoPago(Base):
    __tablename__ = "condicion_pronto_pago"
    __table_args__ = (
        Index(
            "uq_condicion_pronto_pago_vigente",
            "empresa_id",
            "tercero_id",
            unique=True,
            postgresql_where=text("vigente"),
            sqlite_where=text("vigente = 1"),
        ),
        UniqueConstraint("empresa_id", "id"),
        CheckConstraint("plazo_dias > 0", name="plazo_dias_positive"),
        CheckConstraint("porcentaje > 0 AND porcentaje <= 100", name="porcentaje_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    plazo_dias: Mapped[int] = mapped_column(Integer, nullable=False)
    porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    vigente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    override_factura_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)