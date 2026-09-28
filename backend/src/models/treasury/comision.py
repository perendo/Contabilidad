"""ComisionBancaria model (SPEC-021 US2): desglose de comisiones por cobro.

Registro opcional de tracking detallado asociado a un ``CobroMedio``: banco,
tipo de comisión, importe, porcentaje aplicado y cuenta contable de gasto
(626 por defecto). ``importe >= 0`` y coherente con la comisión del cobro.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoComision(str, Enum):
    TPV = "TPV"
    TRANSFERENCIA = "TRANSFERENCIA"
    CHEQUE = "CHEQUE"
    CAJA = "CAJA"
    OTRA = "OTRA"


class ComisionBancaria(Base):
    __tablename__ = "comision_bancaria"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_comision_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id", "cobro_medio_id"],
            ["cobro_medio.empresa_id", "cobro_medio.id"],
            name="fk_comision_cobro_medio",
        ),
        CheckConstraint("importe >= 0", name="chk_comision_importe_no_negativo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cobro_medio_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    banco_codigo: Mapped[str | None] = mapped_column(String(12), nullable=True)
    tipo_comision: Mapped[str] = mapped_column(
        String(50), nullable=False, default="OTRA"
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cuenta_contable: Mapped[str] = mapped_column(String(12), nullable=False, default="626")
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )