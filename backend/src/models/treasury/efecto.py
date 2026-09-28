"""Efecto model (SPEC-021 US1): cheque, pagaré o letra con ciclo de vida.

Un efecto se registra con estado ``emitido`` y al vencimiento se liquida:
cobro -> asiento 572/431 y estado ``cobrado``, o impago -> asiento REVERSAL
(431 [+626] / 572) y estado ``impagado``. Los estados ``cobrado`` e
``impagado`` son finales (inmutables, constitución II).

Multi-tenant estricto (constitución III): ``empresa_id`` en claves, índices
y filtros; el documento es único por (empresa, tercero, tipo).
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


class TipoEfecto(str, Enum):
    CHEQUE = "CHEQUE"
    PAGARE = "PAGARE"
    LETRA = "LETRA"


class EstadoEfecto(str, Enum):
    emitido = "emitido"
    cobrado = "cobrado"
    impagado = "impagado"


class Efecto(Base):
    __tablename__ = "efecto"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_efecto_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "tercero_id",
            "tipo_efecto",
            "numero_documento",
            name="uq_efecto_documento",
        ),
        CheckConstraint("importe > 0", name="chk_efecto_importe_positivo"),
        CheckConstraint(
            "fecha_vencimiento >= fecha_emision", name="chk_efecto_fechas"
        ),
        Index(
            "ix_efecto_empresa_estado_fecha",
            "empresa_id",
            "estado",
            "fecha_vencimiento",
        ),
        Index("ix_efecto_empresa_tercero", "empresa_id", "tercero_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tipo_efecto: Mapped[TipoEfecto] = mapped_column(
        SqlEnum(TipoEfecto, name="tipo_efecto"), nullable=False
    )
    numero_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    estado: Mapped[EstadoEfecto] = mapped_column(
        SqlEnum(EstadoEfecto, name="efecto_estado"),
        nullable=False,
        default=EstadoEfecto.emitido,
    )
    asiento_cobro_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    asiento_impago_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )