"""LineaDivisa (SPEC-016 · US1): importes por línea del asiento en divisa.

Cada fila de JournalEntryLine de un asiento registrado en divisa tiene su
equivalente: ``importe_divisa`` (lo que el cliente introdujo) e
``importe_funcional`` (convertido a 4 decimales). La línea de redondeo
(``es_linea_redondeo``) equilibra el contravalor funcional y no tiene importe
en divisa (constitución I).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKeyConstraint,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class LineaDivisa(Base):
    __tablename__ = "linea_divisa"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_linea_divisa_empresa_id"),
        UniqueConstraint(
            "empresa_id",
            "asiento_divisa_id",
            "linea_id",
            name="uq_linea_divisa_por_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_divisa_id"],
            ["asiento_divisa.empresa_id", "asiento_divisa.id"],
            name="fk_linea_divisa_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "linea_id"],
            ["journal_entry_line.empresa_id", "journal_entry_line.id"],
            name="fk_linea_divisa_linea",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asiento_divisa_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    linea_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    importe_divisa: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    importe_funcional: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    es_linea_redondeo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )