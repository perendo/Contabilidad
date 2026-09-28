"""FiscalYear model (SPEC-004 scaffold consumed by SPEC-002 exercise guards).

Aligned with `005_fiscal_invoice.sql`: multi-tenant, `UNIQUE (empresa_id, year)`
and a date range check. Only the guard fields are exercised by SPEC-002
(create/post/reverse reject closed exercises with HTTP 400); full lifecycle
(open/close, regularización) belongs to SPEC-004.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class FiscalYear(Base):
    __tablename__ = "fiscal_year"
    __table_args__ = (
        UniqueConstraint("empresa_id", "year", name="uq_fiscal_year_empresa_year"),
        CheckConstraint("date_end >= date_start", name="chk_fiscal_year_rango"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    date_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_end: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    regularizacion_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    cierre_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )