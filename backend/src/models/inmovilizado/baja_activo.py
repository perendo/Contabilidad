"""Modelo BajaActivo (SPEC-014): registro de baja/venta con su asiento.

``valor_neto_contable = coste - amortizacion_acumulada`` y
``resultado = precio_venta - valor_neto_contable`` (positivo -> 771, negativo ->
671). Valores en ``Numeric(18,4)``; una sola baja por activo
(``(empresa_id, activo_id)`` único).
"""

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
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoBaja(str, enum.Enum):
    venta = "venta"
    retirada = "retirada"


class BajaActivo(Base):
    __tablename__ = "baja_activo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "activo_id", name="uq_baja_activo"),
        CheckConstraint("precio_venta >= 0", name="chk_baja_precio_no_negativo"),
        CheckConstraint(
            "amortizacion_hasta_baja >= 0", name="chk_baja_amortizacion_no_negativa"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "activo_id"],
            ["activo_inmovilizado.empresa_id", "activo_inmovilizado.id"],
            name="fk_baja_activo",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_baja_asiento",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    fecha_baja: Mapped[date] = mapped_column(Date, nullable=False)
    precio_venta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amortizacion_hasta_baja: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amortizacion_acumulada: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_neto_contable: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    resultado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    asiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tipo: Mapped[TipoBaja] = mapped_column(
        SqlEnum(TipoBaja, name="tipo_baja"), nullable=False
    )