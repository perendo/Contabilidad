"""Correlative asiento numbering per (empresa, ejercicio) (SPEC-002).

Row locked with SELECT ... FOR UPDATE inside the same ACID transaction that
assigns the number, so concurrent posts never skip or repeat numbers.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class SecuenciaAsiento(Base):
    __tablename__ = "journal_sequence"
    __table_args__ = (UniqueConstraint("empresa_id", "ejercicio", name="uq_journal_sequence_pair"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    ultimo_numero: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )