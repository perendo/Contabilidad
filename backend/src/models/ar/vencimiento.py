"""Vencimiento model (SPEC-011 scaffold): the receivable grouped into a remesa.

Minimal subset for SPEC-020 US1: status, due-date (charge date), IBAN and the
exercise are the fields the remittance flow depends on.
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


class EstadoVencimiento(str, Enum):
    pendiente = "pendiente"
    parcial = "parcial"
    cobrado = "cobrado"
    remesado = "remesado"
    devuelto = "devuelto"
    anulado = "anulado"
    cedido = "cedido"


class TipoVencimiento(str, Enum):
    cobro = "cobro"
    pago = "pago"


class Vencimiento(Base):
    __tablename__ = "vencimiento"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        CheckConstraint("importe > 0", name="importe_positive"),
        CheckConstraint("acumulado >= 0 AND acumulado <= importe", name="acumulado_rango"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    factura_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    fecha_factura: Mapped[date | None] = mapped_column(Date, nullable=True)
    recibo_num: Mapped[str] = mapped_column(String(32), nullable=False)
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[TipoVencimiento] = mapped_column(
        SqlEnum(TipoVencimiento, name="vencimiento_tipo"),
        nullable=False,
        default=TipoVencimiento.cobro,
    )
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    acumulado: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0.0000")
    )
    estado: Mapped[EstadoVencimiento] = mapped_column(
        SqlEnum(EstadoVencimiento, name="vencimiento_estado"), nullable=False
    )
    remesa_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def saldo_pendiente(self) -> Decimal:
        """Derived: importe - acumulado (never negative by CHECK)."""
        return self.importe - self.acumulado