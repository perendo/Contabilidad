"""Invoice entity (SPEC-004 US4): exact-amount support document with atomic numbering.

Aligned with `005_fiscal_invoice.sql`: multi-tenant, `UNIQUE
(empresa_id, ejercicio, numero_seq)`, `CHECK (total = base + cuota_iva)` and
a composite FK `(empresa_id, asiento_id)` to the journal entry that backs it.
Once linked (`asiento_id` set) the link is immutable (service-guarded).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class InvoiceTipo(str, enum.Enum):
    emitida = "emitida"
    recibida = "recibida"


class Invoice(Base):
    __tablename__ = "invoice"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "ejercicio", "numero_seq",
            name="uq_invoice_empresa_ejercicio_numero",
        ),
        CheckConstraint("total = base + cuota_iva", name="chk_invoice_total"),
        CheckConstraint("base >= 0", name="chk_invoice_base_non_negative"),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_invoice_asiento",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tipo: Mapped[InvoiceTipo] = mapped_column(
        SqlEnum(InvoiceTipo, name="invoice_tipo"), nullable=False
    )
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nif_tercero: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    cuota_iva: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
