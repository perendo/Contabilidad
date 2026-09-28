"""MovimientoCaja y Arqueo models (SPEC-019 US3).

`movimiento_caja` es una traza derivada del diario (no duplica importes): se
materializa en la misma transaccion del asiento del motor que afecta a una 570
asignada y es inmutable (append-only). `arqueo` contrasta el saldo contable de
la 570 con el efectivo contado; `cuadra` se aprueba sin asiento,
`con_diferencia` requiere asiento de ajuste al aprobar (D6).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class MovimientoTipo(str, Enum):
    entrada = "entrada"
    salida = "salida"


class ArqueoEstado(str, Enum):
    cuadra = "cuadra"
    con_diferencia = "con_diferencia"


class ArqueoDecision(str, Enum):
    pendiente = "pendiente"
    aprobada = "aprobada"
    archivada = "archivada"


class MovimientoCaja(Base):
    __tablename__ = "movimiento_caja"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_movimiento_caja_empresa_id"),
        UniqueConstraint(
            "empresa_id", "asiento_id", "linea_id", name="uq_movimiento_caja_asiento_linea"
        ),
        CheckConstraint("importe > 0", name="chk_movimiento_caja_importe_positivo"),
        ForeignKeyConstraint(
            ["empresa_id", "caja_id"],
            ["caja.empresa_id", "caja.id"],
            name="fk_movimiento_caja_caja",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_movimiento_caja_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "linea_id"],
            ["journal_entry_line.empresa_id", "journal_entry_line.id"],
            name="fk_movimiento_caja_linea",
        ),
        Index("ix_movimiento_caja_empresa_caja", "empresa_id", "caja_id"),
        Index("ix_movimiento_caja_empresa_fecha", "empresa_id", "caja_id", "fecha"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    caja_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    linea_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tipo: Mapped[MovimientoTipo] = mapped_column(
        SqlEnum(MovimientoTipo, name="movimiento_caja_tipo"), nullable=False
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Arqueo(Base):
    __tablename__ = "arqueo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_arqueo_empresa_id"),
        CheckConstraint("efectivo_contado >= 0", name="chk_arqueo_efectivo_positivo"),
        ForeignKeyConstraint(
            ["empresa_id", "caja_id"],
            ["caja.empresa_id", "caja.id"],
            name="fk_arqueo_caja",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_ajuste_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_arqueo_ajuste",
        ),
        Index("ix_arqueo_empresa_caja", "empresa_id", "caja_id", "fecha"),
        Index("ix_arqueo_empresa_estado", "empresa_id", "estado", "decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    caja_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    saldo_libros: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    efectivo_contado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    diferencia: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estado: Mapped[ArqueoEstado] = mapped_column(
        SqlEnum(ArqueoEstado, name="arqueo_estado"), nullable=False
    )
    decision: Mapped[ArqueoDecision | None] = mapped_column(
        SqlEnum(ArqueoDecision, name="arqueo_decision"), nullable=True
    )
    asiento_ajuste_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    archivado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detalle_diferencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )