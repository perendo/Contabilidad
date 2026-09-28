"""Modelo ActivoInmovilizado (SPEC-014): elemento del inmovilizado (cuenta 21x).

Multi-tenant estricto (constitución III): ``empresa_id`` participa en la clave
compuesta ``(empresa_id, id)``, en la unicidad de ``numero_activo`` y en las FKs
compuestas al plan de cuentas (SPEC-001). Importes en ``Numeric(18,4)``;
porcentajes en ``Numeric(5,2)``; prohibido ``float`` (constitución regla fiscal).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class MetodoAmortizacion(str, enum.Enum):
    lineal = "lineal"
    regresivo = "regresivo"


class EstadoActivo(str, enum.Enum):
    en_uso = "en_uso"
    dado_de_baja = "dado_de_baja"


class ActivoInmovilizado(Base):
    __tablename__ = "activo_inmovilizado"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_activo_tenant_id"),
        UniqueConstraint("empresa_id", "numero_activo", name="uq_activo_tenant_numero"),
        CheckConstraint("coste_amortizable > 0", name="chk_activo_coste_positive"),
        CheckConstraint("vida_util > 0", name="chk_activo_vida_positive"),
        CheckConstraint(
            "(metodo = 'regresivo' AND porcentaje_regresivo IS NOT NULL)"
            " OR (metodo = 'lineal' AND porcentaje_regresivo IS NULL)",
            name="chk_activo_metodo_porcentaje",
        ),
        CheckConstraint(
            "porcentaje_regresivo IS NULL"
            " OR (porcentaje_regresivo > 0 AND porcentaje_regresivo < 100)",
            name="chk_activo_porcentaje_rango",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_activo_cuenta",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_gasto_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_activo_cuenta_gasto",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_acumulada_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_activo_cuenta_acumulada",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    numero_activo: Mapped[str] = mapped_column(String(40), nullable=False)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_alta: Mapped[date] = mapped_column(Date, nullable=False)
    coste_amortizable: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    vida_util: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    metodo: Mapped[MetodoAmortizacion] = mapped_column(
        SqlEnum(MetodoAmortizacion, name="metodo_amortizacion"), nullable=False
    )
    porcentaje_regresivo: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    estado: Mapped[EstadoActivo] = mapped_column(
        SqlEnum(EstadoActivo, name="estado_activo"),
        nullable=False,
        default=EstadoActivo.en_uso,
    )
    fecha_baja: Mapped[date | None] = mapped_column(Date, nullable=True)
    cuenta_gasto_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cuenta_acumulada_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)