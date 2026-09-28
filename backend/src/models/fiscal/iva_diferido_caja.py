"""IVADiferidoCaja (SPEC-012 T008): trazabilidad del IVA diferido por caja."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoDiferido(str, enum.Enum):
    diferido = "diferido"
    liquidado = "liquidado"


class IVADiferidoCaja(Base):
    __tablename__ = "iva_diferido_caja"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_iva_diferido_caja_tenant_id"),
        UniqueConstraint(
            "empresa_id", "factura_id", name="uq_iva_diferido_caja_factura"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    factura_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    vencimiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    cuota_diferida: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fecha_devengo_real: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoDiferido] = mapped_column(
        SqlEnum(EstadoDiferido, name="estado_diferido"),
        nullable=False,
        default=EstadoDiferido.diferido,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )