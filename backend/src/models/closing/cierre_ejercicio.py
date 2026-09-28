"""CierreEjercicio (SPEC-028 T007): registro del cierre anual completo.

Integracion con SPEC-004 (regularizacion y cierre) y SPEC-009 (apertura del
siguiente ejercicio, research D5). Los tres asientos se crean POSTED e
inmutables en la misma transaccion ACID que la fila de cierre y el audit log.

`UNIQUE (empresa_id, ejercicio)` da la idempotencia del flujo: reintentar el
cierre de un ejercicio ya cerrado devuelve 409 sin generar duplicados.
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
    Index,
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


class EstadoCierreEjercicio(str, Enum):
    completado = "completado"
    reapertura_pendiente = "reapertura_pendiente"


class CierreEjercicio(Base):
    __tablename__ = "cierre_ejercicio"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_cierre_ejercicio_empresa_id"),
        UniqueConstraint("empresa_id", "ejercicio", name="uq_cierre_ejercicio_ejercicio"),
        CheckConstraint("ejercicio >= 2000 AND ejercicio <= 2100", name="chk_cierre_ejercicio_rango"),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_regularizacion_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_cierre_ejercicio_regularizacion",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_cierre_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_cierre_ejercicio_cierre",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_apertura_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_cierre_ejercicio_apertura",
        ),
        Index("ix_cierre_ejercicio_empresa_ejercicio", "empresa_id", "ejercicio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[EstadoCierreEjercicio] = mapped_column(
        SqlEnum(EstadoCierreEjercicio, name="estado_cierre_ejercicio"),
        nullable=False,
        default=EstadoCierreEjercicio.completado,
    )
    fecha_cierre: Mapped[date] = mapped_column(Date, nullable=False)
    resultado_ejercicio: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    asiento_regularizacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    asiento_cierre_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    asiento_apertura_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    cerrado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cerrado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
