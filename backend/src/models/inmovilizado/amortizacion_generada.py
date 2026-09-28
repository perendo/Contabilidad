"""Modelo AmortizacionGenerada (SPEC-014): asiento 681/281 por activo y período.

Garantiza la antidupilcación (FR-003): solo puede existir una generación
*cORRIENTE* (``reapertura_de IS NULL``, ``reabierta = false``) por
``(empresa_id, activo_id, ejercicio, periodo)``. Al reabrir un período, la
generación previa se marca ``reabierta`` y la posterior enlaza con
``reapertura_de`` (trazabilidad, constitución II).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class AmortizacionGenerada(Base):
    __tablename__ = "amortizacion_generada"
    __table_args__ = (
        ForeignKeyConstraint(
            ["empresa_id", "activo_id"],
            ["activo_inmovilizado.empresa_id", "activo_inmovilizado.id"],
            name="fk_generada_activo",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_generada_asiento",
        ),
        Index(
            "uq_generada_activo_periodo_vigente",
            "empresa_id",
            "activo_id",
            "ejercicio",
            "periodo",
            unique=True,
            sqlite_where=text("reabierta = 0"),
            postgresql_where=text("reabierta = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo: Mapped[int] = mapped_column(Integer, nullable=False)
    asiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cuota: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reapertura_de: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reabierta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )