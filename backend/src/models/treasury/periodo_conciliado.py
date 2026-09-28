"""PeriodoConciliado (SPEC-013): período archivado con diferencia cero."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class PeriodoConciliado(Base):
    __tablename__ = "periodo_conciliado"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        UniqueConstraint(
            "empresa_id", "ejercicio", "numero_periodo", name="uq_periodo_numero"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "conciliacion_id"],
            ["conciliacion.empresa_id", "conciliacion.id"],
            name="fk_periodo_empresa_conciliacion",
        ),
        CheckConstraint("diferencia = 0", name="chk_periodo_diferencia_cero"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    conciliacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_periodo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    saldo_banco: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    saldo_libros: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    diferencia: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fecha_cierre: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
