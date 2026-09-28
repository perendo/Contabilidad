"""MovimientoBancario (SPEC-013): línea del extracto."""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class SignoMovimiento(str, enum.Enum):
    D = "D"
    H = "H"


class EstadoMovimiento(str, enum.Enum):
    pendiente = "pendiente"
    conciliado = "conciliado"
    alertado = "alertado"


class MovimientoBancario(Base):
    __tablename__ = "movimiento_bancario"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        UniqueConstraint(
            "empresa_id", "extracto_id", "orden", name="uq_movimiento_extracto_orden"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "extracto_id"],
            ["extracto_bancario.empresa_id", "extracto_bancario.id"],
            name="fk_movimiento_empresa_extracto",
        ),
        CheckConstraint("importe > 0", name="movimiento_importe_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    extracto_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_operacion: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_valor: Mapped[date | None] = mapped_column(Date, nullable=True)
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    signo: Mapped[SignoMovimiento] = mapped_column(
        SqlEnum(SignoMovimiento, name="movimiento_signo"), nullable=False
    )
    referencia: Mapped[str | None] = mapped_column(String(80), nullable=True)
    estado: Mapped[EstadoMovimiento] = mapped_column(
        SqlEnum(EstadoMovimiento, name="movimiento_estado"),
        nullable=False,
        default=EstadoMovimiento.pendiente,
    )
