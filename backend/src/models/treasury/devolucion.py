"""DevolucionRecibo and Reclamacion models: R19/C19 refunds and claim tracking."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoReclamacion(str, Enum):
    sin_reclamacion = "sin_reclamacion"
    reclamada = "reclamada"
    resuelta = "resuelta"
    desestimada = "desestimada"


class DevolucionRecibo(Base):
    __tablename__ = "devolucion_recibo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "identificador_externo"),
        UniqueConstraint("empresa_id", "id"),
        ForeignKeyConstraint(
            ["empresa_id", "recibo_remesa_id"],
            ["recibo_remesa.empresa_id", "recibo_remesa.id"],
            name="fk_devolucion_empresa_recibo",
        ),
        CheckConstraint("importe >= 0", name="importe_non_negative"),
        CheckConstraint("importe_gastos >= 0", name="importe_gastos_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    recibo_remesa_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    identificador_externo: Mapped[str] = mapped_column(String(64), nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_registro: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_cargo_original: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    importe_gastos: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    asiento_reversal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estado_reclamacion: Mapped[EstadoReclamacion] = mapped_column(
        SqlEnum(EstadoReclamacion, name="estado_reclamacion"), nullable=False
    )


class EstadoReclamacionRec(str, Enum):
    abierta = "abierta"
    en_curso = "en_curso"
    resuelta = "resuelta"
    desestimada = "desestimada"


class Reclamacion(Base):
    __tablename__ = "reclamacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        ForeignKeyConstraint(
            ["empresa_id", "devolucion_id"],
            ["devolucion_recibo.empresa_id", "devolucion_recibo.id"],
            name="fk_reclamacion_empresa_devolucion",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    devolucion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fecha_registro: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoReclamacionRec] = mapped_column(
        SqlEnum(EstadoReclamacionRec, name="reclamacion_estado"), nullable=False
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)