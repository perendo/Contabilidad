"""Ejercicio contable y estado del ciclo (SPEC-009 apertura del ejercicio).

Modelo multi-tenant que gestiona el ciclo contable por (empresa_id, ejercicio):
rango de fechas y estado (abierto -> cerrado -> con_apertura). Tras la
generación del asiento de apertura se deja constancia del asiento ``OPENING``
y, si procede, del ``OPENING_REVERSAL`` de su anulación (constitución II: el
original nunca se modifica).
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
    Integer,
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


class EjercicioEstado(str, Enum):
    abierto = "abierto"
    cerrado = "cerrado"
    con_apertura = "con_apertura"


class EjercicioContable(Base):
    __tablename__ = "ejercicio_contable"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_ejercicio_contable_tenant_id"),
        UniqueConstraint(
            "empresa_id", "ejercicio", name="uq_ejercicio_contable_tenant_ejercicio"
        ),
        CheckConstraint("fecha_inicio < fecha_fin", name="chk_ejercicio_contable_rango"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EjercicioEstado] = mapped_column(
        SqlEnum(EjercicioEstado, name="ejercicio_estado"), nullable=False
    )
    apertura_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    apertura_reversal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )