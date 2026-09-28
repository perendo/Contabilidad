"""ConfiguracionFiscal (SPEC-012): regimenes especiales y cuenta de recargo."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ConfiguracionFiscal(Base):
    __tablename__ = "configuracion_fiscal"
    __table_args__ = (
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_configuracion_fiscal_empresa",
        ),
        CheckConstraint(
            "tipo_is > 0 AND tipo_is <= 100",
            name="chk_configuracion_fiscal_tipo_is",
        ),
        CheckConstraint(
            "fecha_vigencia_hasta IS NULL OR fecha_vigencia_hasta >= fecha_vigencia_desde",
            name="chk_configuracion_fiscal_vigencia",
        ),
    )

    empresa_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recargo_equivalencia_habilitado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    cuenta_recargo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    criterio_caja_habilitado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    tipo_is: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("25.00"),
        server_default=text("25.00"),
    )
    fecha_vigencia_desde: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        default=date.today,
        server_default=func.current_date(),
    )
    fecha_vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
