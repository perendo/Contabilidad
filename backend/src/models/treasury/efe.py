"""InformeEFE y LineaEFE (SPEC-027 T008): Estado de Flujos de Efectivo.

A diferencia del EFE por linea de SPEC-010 (`clasificacion_efe`, que reparte
cada apunte de tesoreria por su contrapartida), este informe es **por cuenta**:
cada `LineaEFE` agrega el saldo del ejercicio de una cuenta del plan y lo
clasifica en un bloque de actividad (research D4: operativa = grupos 6/7 y
tesoreria, inversion = grupo 2, financiacion = grupos 1/9 y deudas 16/17).
`override_usuario` deja traza de cuando el usuario reclasifico la cuenta.

`InformeEFE` es un **snapshot** del ejercicio: al formularse pasa a
`formulado` y queda inmutable (constitucion II), garantizado por triggers
append-only en `migrations/018_cashflow.sql` y su espejo en `db/triggers.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
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


class EstadoInformeEFE(str, Enum):
    borrador = "borrador"
    formulado = "formulado"


class BloqueEFE(str, Enum):
    operativa = "operativa"
    inversion = "inversion"
    financiacion = "financiacion"


class InformeEFE(Base):
    __tablename__ = "informe_efe"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_informe_efe_empresa_id"),
        # Un solo EFE por empresa y ejercicio (research D7).
        UniqueConstraint("empresa_id", "ejercicio", name="uq_informe_efe_ejercicio"),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_informe_efe_empresa",
        ),
        Index("ix_informe_efe_empresa_ejercicio", "empresa_id", "ejercicio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_inicial: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    saldo_final: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    variacion_neta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    cuadre: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sin_conciliar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saldo_conciliacion: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    estado: Mapped[EstadoInformeEFE] = mapped_column(
        SqlEnum(EstadoInformeEFE, name="informe_efe_estado"),
        nullable=False,
        default=EstadoInformeEFE.borrador,
    )
    formulado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fecha_formulacion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LineaEFE(Base):
    __tablename__ = "linea_efe"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_linea_efe_empresa_id"),
        # Una cuenta, un bloque por informe (data-model: validaciones de LineaEFE).
        UniqueConstraint(
            "empresa_id", "informe_id", "cuenta_id", name="uq_linea_efe_informe_cuenta"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "informe_id"],
            ["informe_efe.empresa_id", "informe_efe.id"],
            name="fk_linea_efe_informe",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_linea_efe_cuenta",
        ),
        Index("ix_linea_efe_empresa_informe", "empresa_id", "informe_id"),
        Index("ix_linea_efe_empresa_bloque", "empresa_id", "bloque"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    informe_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    bloque: Mapped[BloqueEFE] = mapped_column(
        SqlEnum(BloqueEFE, name="linea_efe_bloque"), nullable=False
    )
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codigo_cuenta: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    importe: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    override_usuario: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
