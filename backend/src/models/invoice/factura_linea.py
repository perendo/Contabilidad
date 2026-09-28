"""FacturaLinea model (SPEC-007 T008): linea de factura con impuestos.

Importes en ``NUMERIC(18,4)`` (tipos impositivos ``NUMERIC(5,2)``). Checks de
integridad: ``cantidad > 0``, ``precio_unitario > 0`` y descuento en
``[0, 100]``. Multi-tenant: FK compuesta ``(empresa_id, factura_id)``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base
from models.fiscal.retencion import TipoRetencion


class FacturaLinea(Base):
    __tablename__ = "factura_linea"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_factura_linea_tenant_id"),
        ForeignKeyConstraint(
            ["empresa_id", "factura_id"],
            ["factura.empresa_id", "factura.id"],
            name="fk_factura_linea_factura",
        ),
        CheckConstraint("cantidad > 0", name="chk_factura_linea_cantidad"),
        CheckConstraint("precio_unitario > 0", name="chk_factura_linea_precio"),
        CheckConstraint(
            "porcentaje_descuento BETWEEN 0 AND 100", name="chk_factura_linea_descuento"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    factura_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    porcentaje_descuento: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal(0)
    )
    base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    tipo_iva: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal(0))
    cuota_iva: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    tipo_recargo: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal(0)
    )
    cuota_recargo: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    tipo_irpf: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal(0))
    base_irpf: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    cuota_irpf: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    tipo_retencion: Mapped[TipoRetencion | None] = mapped_column(
        SqlEnum(TipoRetencion, name="tipo_retencion_irpf"),
        nullable=True,
        default=TipoRetencion.IRPF_OTROS,
        server_default=TipoRetencion.IRPF_OTROS.value,
    )
    direccion_inmueble: Mapped[str | None] = mapped_column(String(200), nullable=True)
