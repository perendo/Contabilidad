"""Importes presupuestarios por combinacion cuenta-centro-ejercicio (SPEC-026).

FR-001/FR-005: una unica linea por `(empresa_id, ejercicio, cuenta_id,
centro_coste_id)`. `centro_coste_id` es opcional (FR-006) y por eso la
unicidad se resuelve con DOS indices parciales: en SQL, NULL no colisiona, de
modo que un unico indice compuesto permitiria duplicar las lineas sin centro
(que son precisamente las mas comunes cuando la empresa no usa centros).

Los importes son `NUMERIC(18,4)` / `Decimal` (constitucion: prohibido `float`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
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


class TipoPresupuesto(str, Enum):
    gasto = "gasto"
    ingreso = "ingreso"


class Presupuesto(Base):
    __tablename__ = "presupuesto"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_presupuesto_empresa_id"),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_presupuesto_cuenta",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "centro_coste_id"],
            ["centro_coste.empresa_id", "centro_coste.id"],
            name="fk_presupuesto_centro",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "periodo_id"],
            ["periodo_seguimiento.empresa_id", "periodo_seguimiento.id"],
            name="fk_presupuesto_periodo",
        ),
        # FR-005: unicidad de la combinacion. Dos indices parciales porque
        # `centro_coste_id` es NULLABLE (NULL no colisiona en un UNIQUE normal).
        Index(
            "uq_presupuesto_sin_centro",
            "empresa_id",
            "ejercicio",
            "cuenta_id",
            unique=True,
            sqlite_where=text("centro_coste_id IS NULL"),
            postgresql_where=text("centro_coste_id IS NULL"),
        ),
        Index(
            "uq_presupuesto_con_centro",
            "empresa_id",
            "ejercicio",
            "cuenta_id",
            "centro_coste_id",
            unique=True,
            sqlite_where=text("centro_coste_id IS NOT NULL"),
            postgresql_where=text("centro_coste_id IS NOT NULL"),
        ),
        Index("ix_presupuesto_empresa_ejercicio", "empresa_id", "ejercicio"),
        Index("ix_presupuesto_empresa_centro", "empresa_id", "centro_coste_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    centro_coste_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    periodo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    importe: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    tipo: Mapped[TipoPresupuesto] = mapped_column(
        SqlEnum(TipoPresupuesto, name="tipo_presupuesto"),
        nullable=False,
        default=TipoPresupuesto.gasto,
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
