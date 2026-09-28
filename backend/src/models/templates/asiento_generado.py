"""Immutable trace linking a posted journal entry to its template version."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class AsientoGenerado(Base):
    __tablename__ = "asiento_generado"
    __table_args__ = (
        ForeignKeyConstraint(
            ["empresa_id", "plantilla_id"],
            ["plantilla_asiento.empresa_id", "plantilla_asiento.id"],
            name="fk_asiento_generado_empresa_plantilla",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_asiento_generado_empresa_asiento",
        ),
        Index("ix_asiento_generado_empresa", "empresa_id"),
        Index("ix_asiento_generado_empresa_plantilla", "empresa_id", "plantilla_id"),
    )

    empresa_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    plantilla_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version_plantilla: Mapped[int] = mapped_column(BigInteger, nullable=False)
    variables_aportadas: Mapped[dict] = mapped_column(JSON, nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    usuario_generador: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
