"""Conciliacion y CruceConciliacion (SPEC-013)."""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ConciliacionEstado(str, enum.Enum):
    abierta = "abierta"
    cerrada = "cerrada"


class CruceOrigen(str, enum.Enum):
    auto = "auto"
    manual = "manual"


class CrucePrioridad(str, enum.Enum):
    propuesto = "propuesto"
    candidato = "candidato"


class CruceEstado(str, enum.Enum):
    pendiente_confirmar = "pendiente_confirmar"
    confirmado = "confirmado"


class Conciliacion(Base):
    __tablename__ = "conciliacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        CheckConstraint(
            "diferencia = saldo_banco - saldo_libros", name="chk_conciliacion_diferencia"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    extracto_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    saldo_banco: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    saldo_libros: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    diferencia: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estado: Mapped[ConciliacionEstado] = mapped_column(
        SqlEnum(ConciliacionEstado, name="conciliacion_estado"),
        nullable=False,
        default=ConciliacionEstado.abierta,
    )
    periodo_conciliado_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class CruceConciliacion(Base):
    __tablename__ = "cruce_conciliacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        UniqueConstraint("empresa_id", "movimiento_id", name="uq_cruce_empresa_movimiento"),
        ForeignKeyConstraint(
            ["empresa_id", "conciliacion_id"],
            ["conciliacion.empresa_id", "conciliacion.id"],
            name="fk_cruce_empresa_conciliacion",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "movimiento_id"],
            ["movimiento_bancario.empresa_id", "movimiento_bancario.id"],
            name="fk_cruce_empresa_movimiento",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    conciliacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    movimiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    apunte_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    signo: Mapped[str] = mapped_column(String(1), nullable=False)
    origen: Mapped[CruceOrigen] = mapped_column(
        SqlEnum(CruceOrigen, name="cruce_origen"), nullable=False
    )
    prioridad: Mapped[CrucePrioridad] = mapped_column(
        SqlEnum(CrucePrioridad, name="cruce_prioridad"), nullable=False
    )
    estado: Mapped[CruceEstado] = mapped_column(
        SqlEnum(CruceEstado, name="cruce_estado"),
        nullable=False,
        default=CruceEstado.pendiente_confirmar,
    )
    fecha_cruce: Mapped[date | None] = mapped_column(Date, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confirmado_por_remesa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
