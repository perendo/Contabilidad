from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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


class EstadoCalculoIS(str, Enum):
    borrador = "borrador"
    calculado = "calculado"
    contabilizado = "contabilizado"


class CalculoIS(Base):
    __tablename__ = "calculo_is"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_calculo_is_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_calculo_is_empresa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_calculo_is_asiento",
        ),
        CheckConstraint(
            "tipo_impositivo > 0 AND tipo_impositivo <= 100",
            name="chk_calculo_is_tipo_positivo",
        ),
        CheckConstraint(
            "ajustes_positivos >= 0", name="chk_calculo_is_ajustes_positivos"
        ),
        CheckConstraint(
            "ajustes_negativos >= 0", name="chk_calculo_is_ajustes_negativos"
        ),
        CheckConstraint(
            "deducciones >= 0", name="chk_calculo_is_deducciones"
        ),
        CheckConstraint(
            "pagos_a_cuenta >= 0", name="chk_calculo_is_pagos"
        ),
        Index("ix_calculo_is_empresa_estado", "empresa_id", "estado"),
        Index(
            "uq_calculo_is_definitivo",
            "empresa_id",
            "ejercicio",
            unique=True,
            sqlite_where=text("provisional = 0"),
            postgresql_where=text("provisional = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    resultado_contable: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    ajustes_positivos: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    ajustes_negativos: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    base_imponible: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    tipo_impositivo: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("25.00"), server_default=text("25.00")
    )
    cuota_integra: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    deducciones: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    cuota_liquida: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    pagos_a_cuenta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    cuota_diferencial: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default=text("0")
    )
    provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    estado: Mapped[EstadoCalculoIS] = mapped_column(
        SqlEnum(EstadoCalculoIS, name="calculo_is_estado"),
        nullable=False,
        default=EstadoCalculoIS.borrador,
        server_default=EstadoCalculoIS.borrador.value,
    )
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
