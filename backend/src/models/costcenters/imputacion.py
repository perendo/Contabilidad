"""ImputacionCentro model (SPEC-017 D2/D5): traza de imputación por apunte.

Registro append-only que liga una línea de `journal_entry_line` con un centro de
la empresa activa en el momento de crear/rectificar el asiento. Nunca se
actualiza ni borra (constitución II); solo puede desaparecer cuando el asiento
es un borrador que se cancela. `periodo` = mes del asiento para informes
rápidos por período.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    SmallInteger,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ImputacionCentro(Base):
    __tablename__ = "imputacion_centro"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_imputacion_centro_empresa_id"),
        UniqueConstraint(
            "empresa_id", "asiento_id", "linea_id",
            name="uq_imputacion_centro_linea",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_imputacion_centro_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "linea_id"],
            ["journal_entry_line.empresa_id", "journal_entry_line.id"],
            name="fk_imputacion_centro_linea",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "centro_coste_id"],
            ["centro_coste.empresa_id", "centro_coste.id"],
            name="fk_imputacion_centro_centro",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    linea_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    centro_coste_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    periodo: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )