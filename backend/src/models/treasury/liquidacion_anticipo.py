"""LiquidacionAnticipo model (SPEC-022 US1/US2): aplicación trazable.

Registra cada aplicación de un anticipo contra una factura (Debe 430/410 |
Haber 438/407), con la factura, el importe aplicado y su asiento. La traza
permite auditar cuánto y contra qué factura se aplicó cada anticipo (FR-002).

Multi-tenant estricto (constitución III): ``empresa_id`` en claves, FKs
compuestas e índices. Importes ``NUMERIC(18,4)``/``Decimal``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

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
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class LiquidacionAnticipo(Base):
    __tablename__ = "liquidacion_anticipo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_liquidacion_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id", "anticipo_id"],
            ["anticipo.empresa_id", "anticipo.id"],
            name="fk_liquidacion_anticipo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "factura_id"],
            ["factura.empresa_id", "factura.id"],
            name="fk_liquidacion_factura",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_liquidacion_asiento",
        ),
        CheckConstraint(
            "importe_aplicado > 0", name="chk_liquidacion_importe_positivo"
        ),
        Index("ix_liquidacion_empresa_anticipo", "empresa_id", "anticipo_id"),
        Index("ix_liquidacion_empresa_factura", "empresa_id", "factura_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    anticipo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    factura_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    fecha_aplicacion: Mapped[date] = mapped_column(Date, nullable=False)
    importe_aplicado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )