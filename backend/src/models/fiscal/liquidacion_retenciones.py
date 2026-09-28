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
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoLiquidacionRetenciones(str, Enum):
    pendiente = "pendiente"
    liquidado = "liquidado"


class LiquidacionRetenciones(Base):
    __tablename__ = "liquidacion_retenciones"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "id", name="uq_liquidacion_retenciones_tenant_id"
        ),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "trimestre",
            name="uq_liquidacion_retenciones_ejercicio_trimestre",
        ),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_liquidacion_retenciones_empresa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_liquidacion_retenciones_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "modelo_111_id"],
            ["modelo_111.empresa_id", "modelo_111.id"],
            name="fk_liquidacion_retenciones_modelo_111",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["empresa_id", "modelo_115_id"],
            ["modelo_115.empresa_id", "modelo_115.id"],
            name="fk_liquidacion_retenciones_modelo_115",
            use_alter=True,
        ),
        CheckConstraint(
            "trimestre BETWEEN 1 AND 4", name="chk_liquidacion_retenciones_trimestre"
        ),
        CheckConstraint(
            "total_base_retenciones >= 0",
            name="chk_liquidacion_retenciones_base_no_negativo",
        ),
        CheckConstraint(
            "total_retenciones >= 0",
            name="chk_liquidacion_retenciones_total_no_negativo",
        ),
        CheckConstraint(
            "n_perceptores >= 0", name="chk_liquidacion_retenciones_perceptores"
        ),
        CheckConstraint(
            "estado <> 'liquidado' OR (fecha_liquidacion IS NOT NULL AND asiento_id IS NOT NULL)",
            name="chk_liquidacion_retenciones_liquidado_completo",
        ),
        Index(
            "ix_liquidacion_retenciones_empresa_estado",
            "empresa_id",
            "estado",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    trimestre: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    total_base_retenciones: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    total_retenciones: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    n_perceptores: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    estado: Mapped[EstadoLiquidacionRetenciones] = mapped_column(
        SqlEnum(
            EstadoLiquidacionRetenciones,
            name="estado_liquidacion_retenciones",
        ),
        nullable=False,
        default=EstadoLiquidacionRetenciones.pendiente,
        server_default=EstadoLiquidacionRetenciones.pendiente.value,
    )
    fecha_liquidacion: Mapped[date | None] = mapped_column(Date, nullable=True)
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    modelo_111_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    modelo_115_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
