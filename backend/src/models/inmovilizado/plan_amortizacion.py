"""Modelo PlanAmortizacion (SPEC-014): cuota y acumulado por período.

El acumulado de cada fila no puede superar el coste del activo (FR-006). Esa
regla se refuerza en el servicio (``services/inmovilizado/plan.py``) porque un
CHECK de columna no puede consultar otra tabla y el test
``test_coste_amortizable_tope`` la valida sobre planes reales.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoPlan(str, enum.Enum):
    pendiente = "pendiente"
    amortizado = "amortizado"


class PlanAmortizacion(Base):
    __tablename__ = "plan_amortizacion"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "activo_id", "ejercicio", "periodo", name="uq_plan_activo_periodo"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "activo_id"],
            ["activo_inmovilizado.empresa_id", "activo_inmovilizado.id"],
            name="fk_plan_activo",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo: Mapped[int] = mapped_column(Integer, nullable=False)
    cuota: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    acumulado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estado: Mapped[EstadoPlan] = mapped_column(
        SqlEnum(EstadoPlan, name="estado_plan"),
        nullable=False,
        default=EstadoPlan.pendiente,
    )