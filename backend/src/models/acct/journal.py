"""Accounting journal (SPEC-002) with a compatible superset that also supports
the treasury scaffolds (SPEC-020): immutable POSTED entries, balance-checked
lines, DRAFT flow and correlative numbering.

Constitution notes: balance is validated in the service (closest point to
persistence) and additionally enforced by PG triggers (003_journal.sql);
POSTED/CANCELLED entries are immutable (no UPDATE/DELETE endpoints).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

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


class JournalEntryTipo(str, Enum):
    GENERAL = "GENERAL"
    COBRO = "COBRO"
    PRONTO_PAGO = "PRONTO_PAGO"
    REVERSAL = "REVERSAL"
    ADJUSTMENT = "ADJUSTMENT"
    OPENING = "OPENING"
    OPENING_REVERSAL = "OPENING_REVERSAL"
    # SPEC-028 T009 (research D8): cierre intermedio/paquete de cierre anual.
    # `reverses_id` ya existe como `original_id` (cadena de inmutabilidad) y
    # `cierre_id` como `referencia_cierre_id` (trazabilidad del cierre), de modo
    # que la ampliacion del data-model no anade columnas nuevas.
    REGULARIZACION = "REGULARIZACION"
    CIERRE = "CIERRE"


#: Tipos de asiento que el cierre de SPEC-028 puede emitir aunque la fecha caiga
#: en un periodo bloqueado: el propio cierre debe poder registrarse.
TIPOS_CIERRE: frozenset[JournalEntryTipo] = frozenset(
    {
        JournalEntryTipo.REGULARIZACION,
        JournalEntryTipo.CIERRE,
        JournalEntryTipo.OPENING,
        JournalEntryTipo.OPENING_REVERSAL,
    }
)


class JournalEntryEstado(str, Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class JournalEntry(Base):
    __tablename__ = "journal_entry"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_journal_entry_tenant_id"),
        UniqueConstraint(
            "empresa_id", "ejercicio", "numero_asiento", name="uq_journal_entry_tenant_numero"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[JournalEntryTipo] = mapped_column(
        SqlEnum(JournalEntryTipo, name="journal_entry_tipo"), nullable=False
    )
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    numero_asiento: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    original_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    referencia_cierre_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    estado: Mapped[JournalEntryEstado] = mapped_column(
        SqlEnum(JournalEntryEstado, name="journal_entry_estado"),
        nullable=False,
        default=JournalEntryEstado.POSTED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class JournalEntryLine(Base):
    __tablename__ = "journal_entry_line"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        ForeignKeyConstraint(
            ["empresa_id", "journal_entry_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_journal_line_empresa_entry",
        ),
CheckConstraint("debe >= 0", name="debe_non_negative"),
        CheckConstraint("haber >= 0", name="haber_non_negative"),
        CheckConstraint(
            "(debe > 0 AND haber = 0) OR (debe = 0 AND haber > 0)",
            name="line_debit_xor_credit",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "centro_coste_id"],
            ["centro_coste.empresa_id", "centro_coste.id"],
            name="fk_journal_line_centro_coste",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    account_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cuenta: Mapped[str] = mapped_column(String(16), nullable=False)
    debe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    haber: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    centro_coste_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)