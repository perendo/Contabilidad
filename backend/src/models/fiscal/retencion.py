from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoRetencion(str, Enum):
    IRPF_PROFESIONALES = "IRPF_PROFESIONALES"
    IRPF_ARRENDAMIENTOS = "IRPF_ARRENDAMIENTOS"
    IRPF_OBRAS = "IRPF_OBRAS"
    IRPF_OTROS = "IRPF_OTROS"


class RetencionPeriodo(Base):
    __tablename__ = "retencion_periodo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_retencion_periodo_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_retencion_periodo_empresa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "liquidacion_retenciones_id"],
            [
                "liquidacion_retenciones.empresa_id",
                "liquidacion_retenciones.id",
            ],
            name="fk_retencion_periodo_liquidacion",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "tercero_id"],
            ["tercero.empresa_id", "tercero.id"],
            name="fk_retencion_periodo_tercero",
        ),
        CheckConstraint("base_imponible > 0", name="chk_retencion_periodo_base"),
        CheckConstraint(
            "retencion_practicada > 0", name="chk_retencion_periodo_retencion"
        ),
        CheckConstraint(
            "tipo_porcentaje > 0 AND tipo_porcentaje <= 100",
            name="chk_retencion_periodo_tipo",
        ),
        CheckConstraint(
            "ABS(retencion_practicada - ROUND(base_imponible * tipo_porcentaje / 100, 4)) <= 0.01",
            name="chk_retencion_periodo_formula",
        ),
        Index(
            "ix_retencion_periodo_empresa_liquidacion",
            "empresa_id",
            "liquidacion_retenciones_id",
        ),
        Index(
            "ix_retencion_periodo_empresa_tercero",
            "empresa_id",
            "tercero_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    liquidacion_retenciones_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False
    )
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    nif: Mapped[str | None] = mapped_column(
        String(9), nullable=True, default="", server_default=text("''")
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_retencion: Mapped[TipoRetencion] = mapped_column(
        SqlEnum(TipoRetencion, name="tipo_retencion_irpf"), nullable=False
    )
    base_imponible: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tipo_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    retencion_practicada: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    facturas: Mapped[list[dict[str, object]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
