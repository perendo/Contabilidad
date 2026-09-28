"""PeriodoFiscal (SPEC-012 T005): trimestre o mes del modelo 303 por empresa."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoPeriodo(str, enum.Enum):
    TRIMESTRE = "TRIMESTRE"
    MES = "MES"


class EstadoPeriodo(str, enum.Enum):
    pendiente = "pendiente"
    libros_generados = "libros_generados"
    calculado_303 = "calculado_303"
    exportado = "exportado"


class PeriodoFiscal(Base):
    __tablename__ = "periodo_fiscal"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_periodo_fiscal_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "tipo_periodo",
            "numero_periodo",
            name="uq_periodo_fiscal_numero",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tipo_periodo: Mapped[TipoPeriodo] = mapped_column(
        SqlEnum(TipoPeriodo, name="tipo_periodo"), nullable=False
    )
    numero_periodo: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoPeriodo] = mapped_column(
        SqlEnum(EstadoPeriodo, name="estado_periodo"),
        nullable=False,
        default=EstadoPeriodo.pendiente,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )