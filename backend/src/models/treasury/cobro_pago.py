"""CobroPago (SPEC-011): individual collection/payment linked to an entry."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class CobroPago(Base):
    __tablename__ = "cobro_pago"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        UniqueConstraint(
            "empresa_id", "ejercicio", "numero_operacion", name="uq_cobro_pago_numero"
        ),
        CheckConstraint("importe > 0", name="cobro_pago_importe_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    numero_operacion: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    vencimiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cuenta_tesoreria: Mapped[str] = mapped_column(String(20), nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
