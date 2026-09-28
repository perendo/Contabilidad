"""CobroMedio model (SPEC-021 US2): cobro por TPV/tarjeta/transferencia.

Registra la liquidación de un vencimiento (SPEC-011) por un medio concreto
con comisión bancaria opcional. El asiento generado cuadra
Debe 572 (neto) + 626 (comisión) | Haber 430 (total); ``importe_neto`` es
calculado (total - comisión) y nunca negativo.
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
    Index,
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


class MedioCobro(str, Enum):
    CHEQUE = "CHEQUE"
    PAGARE = "PAGARE"
    LETRA = "LETRA"
    TARJETA = "TARJETA"
    TRANSFERENCIA = "TRANSFERENCIA"
    CAJA = "CAJA"


class CobroMedio(Base):
    __tablename__ = "cobro_medio"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_cobro_medio_tenant_id"),
        CheckConstraint("importe_total > 0", name="chk_cobro_medio_total_positivo"),
        CheckConstraint(
            "importe_comision >= 0", name="chk_cobro_medio_comision_no_negativa"
        ),
        CheckConstraint(
            "importe_comision <= importe_total", name="chk_cobro_medio_comision_lte"
        ),
        CheckConstraint("importe_neto >= 0", name="chk_cobro_medio_neto_no_negativo"),
        Index("ix_cobro_medio_empresa_fecha", "empresa_id", "fecha_cobro"),
        Index("ix_cobro_medio_empresa_medio", "empresa_id", "medio_cobro"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    vencimiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    medio_cobro: Mapped[MedioCobro] = mapped_column(
        SqlEnum(MedioCobro, name="medio_cobro"), nullable=False
    )
    fecha_cobro: Mapped[date] = mapped_column(Date, nullable=False)
    importe_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    importe_comision: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0.0000")
    )
    importe_neto: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cuenta_banco: Mapped[str] = mapped_column(String(12), nullable=False, default="572")
    asiento_cobro_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )