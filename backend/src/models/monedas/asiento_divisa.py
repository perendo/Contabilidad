"""AsientoDivisa (SPEC-016 · US1): cabecera del asiento registrado en divisa.

Vincula un asiento de JournalEntry (POSTED, inmutable) con la divisa y el
TipoCambio sellado que se usó para el equivalente en moneda funcional. Un
asiento de diario solo puede corresponder a una divisa (``asiento_id`` único).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class AsientoDivisa(Base):
    __tablename__ = "asiento_divisa"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_asiento_divisa_empresa_id"),
        UniqueConstraint("empresa_id", "asiento_id", name="uq_asiento_divisa_asiento"),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_asiento_divisa_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "divisa_id"],
            ["moneda.empresa_id", "moneda.id"],
            name="fk_asiento_divisa_moneda",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "tipo_cambio_id"],
            ["tipo_cambio.empresa_id", "tipo_cambio.id"],
            name="fk_asiento_divisa_tipo",
        ),
        CheckConstraint("importe_total_divisa > 0", name="chk_asiento_divisa_importe"),
        CheckConstraint(
            "importe_total_funcional > 0", name="chk_asiento_divisa_importe_funcional"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    divisa_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tipo_cambio_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    importe_total_divisa: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    importe_total_funcional: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )