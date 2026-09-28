"""Anticipo model (SPEC-022 US1/US2): cobros/pagos por anticipado (438/407).

Un anticipo de cliente se cobra registrando el asiento 572/438; un anticipo a
proveedor se paga registrando 407/572. Contra las facturas posteriores se
aplica con una ``LiquidacionAnticipo`` (Debe 430/410 | Haber 438/407) que
reduce el ``saldo_pendiente`` de forma atómica; el exceso queda como saldo a
favor del tercero (FR-003).

Multi-tenant estricto (constitución III): ``empresa_id`` en claves, FKs
compuestas e índices. Importes ``NUMERIC(18,4)``/``Decimal`` (prohibido
``float``).
"""

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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoAnticipo(str, Enum):
    CLIENTE = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"


class EstadoAnticipo(str, Enum):
    pendiente = "pendiente"
    parcialmente_aplicado = "parcialmente_aplicado"
    totalmente_aplicado = "totalmente_aplicado"


class Anticipo(Base):
    __tablename__ = "anticipo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_anticipo_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id", "tercero_id"],
            ["tercero.empresa_id", "tercero.id"],
            name="fk_anticipo_tercero",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_anticipo_asiento",
        ),
        CheckConstraint("importe > 0", name="chk_anticipo_importe_positivo"),
        CheckConstraint(
            "saldo_pendiente >= 0", name="chk_anticipo_saldo_no_negativo"
        ),
        Index(
            "ix_anticipo_empresa_tercero_tipo",
            "empresa_id",
            "tercero_id",
            "tipo",
        ),
        Index("ix_anticipo_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    tipo: Mapped[TipoAnticipo] = mapped_column(
        SqlEnum(TipoAnticipo, name="anticipo_tipo"), nullable=False
    )
    cuenta_contable: Mapped[str] = mapped_column(String(12), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[EstadoAnticipo] = mapped_column(
        SqlEnum(EstadoAnticipo, name="anticipo_estado"),
        nullable=False,
        default=EstadoAnticipo.pendiente,
    )
    saldo_pendiente: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )