"""Caja model (SPEC-019 US3): subcuenta 570 real del plan de la empresa.

Cada caja se enlaza a una subcuenta 570 (1 caja = 1 subcuenta 570, D5) y sus
movimientos son asientos reales del motor (SPEC-002), no apuntes paralelos.
La unicidad de `cuenta_570_id` por empresa impide dos cajas sobre la misma 570.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class CajaTipo(str, Enum):
    caja = "caja"
    caja_chica = "caja_chica"


class CajaEstado(str, Enum):
    activa = "activa"
    inactiva = "inactiva"


class Caja(Base):
    __tablename__ = "caja"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_caja_empresa_id"),
        UniqueConstraint("empresa_id", "nombre", name="uq_caja_empresa_nombre"),
        UniqueConstraint("empresa_id", "cuenta_570_id", name="uq_caja_empresa_570"),
        CheckConstraint("length(nombre) BETWEEN 1 AND 80", name="chk_caja_nombre_len"),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_570_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_caja_cuenta_570",
        ),
        Index("ix_caja_empresa", "empresa_id"),
        Index("ix_caja_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    cuenta_570_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[CajaTipo] = mapped_column(
        SqlEnum(CajaTipo, name="caja_tipo"), nullable=False, default=CajaTipo.caja
    )
    estado: Mapped[CajaEstado] = mapped_column(
        SqlEnum(CajaEstado, name="caja_estado"), nullable=False, default=CajaEstado.activa
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )