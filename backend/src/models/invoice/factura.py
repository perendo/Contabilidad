"""Factura model (SPEC-007 T007): cabecera de factura de venta o compra.

Multi-tenant estricto (constitución III): ``empresa_id`` en claves, FKs
compuestas e índices; los importes son ``NUMERIC(18,4)``/``Decimal``
(prohibido ``float``). Cabecera + lineas se persisten en la misma transacción
ACID que su asiento vinculado (patrón integrado, research D5).

Estados: `borrador` -> `emitida` (irreversible, genera numero + asiento) ->
`anulada` (solo vía rectificativa total). Una `emitida` nunca se borra
(constitución II).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKeyConstraint,
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


class FacturaTipo(str, enum.Enum):
    VENTA = "VENTA"
    COMPRA = "COMPRA"
    RECTIFICATIVA = "RECTIFICATIVA"


class FacturaEstado(str, enum.Enum):
    borrador = "borrador"
    emitida = "emitida"
    anulada = "anulada"


class Factura(Base):
    __tablename__ = "factura"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_factura_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "serie_id",
            "ejercicio",
            "numero",
            name="uq_factura_serie_ejercicio_numero",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "serie_id"],
            ["serie_factura.empresa_id", "serie_factura.id"],
            name="fk_factura_serie",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "tercero_id"],
            ["tercero.empresa_id", "tercero.id"],
            name="fk_factura_tercero",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_factura_asiento",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "factura_original_id"],
            ["factura.empresa_id", "factura.id"],
            name="fk_factura_original",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    serie_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    numero: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[FacturaTipo] = mapped_column(
        SqlEnum(FacturaTipo, name="factura_tipo"), nullable=False
    )
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    factura_original_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    concepto_global: Mapped[str | None] = mapped_column(String(255), nullable=True)
    importe_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    importe_iva: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    importe_recargo: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    importe_irpf: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    importe_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    regimen_caja: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    iva_devengado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    estado: Mapped[FacturaEstado] = mapped_column(
        SqlEnum(FacturaEstado, name="factura_estado"),
        nullable=False,
        default=FacturaEstado.borrador,
    )
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )