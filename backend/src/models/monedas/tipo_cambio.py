"""TipoCambio (SPEC-016 · US1/US2): tipo de cambio por (empresa, divisa, fecha).

Sellado e inmutable: un tipo usado por un asiento POSTED queda ``sellado`` al
postearse (constitución II) y su ``ratio`` ya no se puede modificar ni la fila
eliminar (defensa a nivel DB en ``migrations/008_forex.sql`` y en
``db/triggers.py`` para SQLite). La consistencia ``sellado = (usos > 0)`` se
garantiza con CHECK.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoCambio(Base):
    __tablename__ = "tipo_cambio"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_tipo_cambio_empresa_id"),
        UniqueConstraint(
            "empresa_id",
            "divisa_id",
            "fecha",
            name="uq_tipo_cambio_divisa_fecha",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "divisa_id"],
            ["moneda.empresa_id", "moneda.id"],
            name="fk_tipo_cambio_moneda",
        ),
        CheckConstraint("ratio > 0", name="chk_tipo_cambio_ratio_positivo"),
        CheckConstraint(
            "ratio = ROUND(ratio, 8)", name="chk_tipo_cambio_precision_8"
        ),
        CheckConstraint(
            "(sellado = (usos_posteados > 0))", name="chk_tipo_cambio_sellado_consistente"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    divisa_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    ratio: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    usos_posteados: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sellado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)