"""Periodo de seguimiento presupuestario (SPEC-026 T-04/D5/D8).

Rango de fechas de cotejo con numeracion correlativa por `(empresa_id,
ejercicio)` (constitucion IV). Solo puede haber un periodo `abierto` por
ejercicio, garantia que vive en un indice parcial UNIQUE (la garantia mas
cercana a la persistencia) y que el servicio replica para devolver 409/422
legibles.

Transicion unica e irreversible `abierto -> cerrado`; el cierre materializa el
snapshot inmutable `Desviacion` (constitucion II).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoPeriodo(str, Enum):
    abierto = "abierto"
    cerrado = "cerrado"


class PeriodoSeguimiento(Base):
    __tablename__ = "periodo_seguimiento"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_periodo_seguimiento_empresa_id"),
        # Correlatividad por (empresa, ejercicio) sin saltos (constitucion IV).
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "numero_periodo",
            name="uq_periodo_seguimiento_numero",
        ),
        CheckConstraint("fecha_fin > fecha_inicio", name="chk_periodo_seguimiento_rango"),
        CheckConstraint("numero_periodo > 0", name="chk_periodo_seguimiento_numero_pos"),
        # Solo un periodo abierto por (empresa, ejercicio).
        Index(
            "uq_periodo_seguimiento_abierto",
            "empresa_id",
            "ejercicio",
            unique=True,
            sqlite_where=text("estado = 'abierto'"),
            postgresql_where=text("estado = 'abierto'"),
        ),
        Index(
            "ix_periodo_seguimiento_empresa_ejercicio",
            "empresa_id",
            "ejercicio",
            "numero_periodo",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_periodo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoPeriodo] = mapped_column(
        SqlEnum(EstadoPeriodo, name="periodo_seguimiento_estado"),
        nullable=False,
        default=EstadoPeriodo.abierto,
    )
    fecha_cierre: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cerrado_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    desviaciones_registradas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
