"""GastoImputado model (SPEC-019 US1): asignacion de una linea del diario
inmutable a una subvencion para su justificacion.

No duplica contabilidad: referencia a la linea concreta (`linea_id`) del
asiento POSTED sin tocarla (constitucion II). La suma por linea no supera el
importe de la linea y el acumulado por subvencion no supera el concedido
(validacion en `services/ngo/justificacion.py`, FR-003).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class GastoImputado(Base):
    __tablename__ = "gasto_imputado"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_gasto_imputado_empresa_id"),
        CheckConstraint("importe_asignado > 0", name="chk_gasto_imputado_importe_positivo"),
        ForeignKeyConstraint(
            ["empresa_id", "subvencion_id"],
            ["subvencion.empresa_id", "subvencion.id"],
            name="fk_gasto_imputado_subvencion",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_gasto_imputado_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "linea_id"],
            ["journal_entry_line.empresa_id", "journal_entry_line.id"],
            name="fk_gasto_imputado_linea",
        ),
        Index("ix_gasto_imputado_empresa_subvencion", "empresa_id", "subvencion_id"),
        Index(
            "ix_gasto_imputado_empresa_linea",
            "empresa_id", "subvencion_id", "linea_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subvencion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    linea_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    importe_asignado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    partida: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )