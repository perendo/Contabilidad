"""Snapshot inmutable de desviaciones al cerrar un periodo (SPEC-026 T-04/D5).

Espejo exacto de `Presupuesto + SUM(journal_entry_line)` en el instante del
cierre. La tabla solo crece: no se actualiza ni se borra nunca (constitucion
II), garantia reforzada por triggers append-only en PostgreSQL
(`017_presupuestos.sql`) y en SQLite (`db/triggers.py`).

`desviacion_relativa` es un ratio decimal `NUMERIC(7,4)`; es `NULL` cuando el
presupuesto es 0 (dividir entre cero no tiene sentido financiero, D4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base

#: Rango del ratio `NUMERIC(7,4)`; se satura para no romper la columna cuando
#: el real supera 1.000.000x el presupuesto (economicamente absurdo).
RATIO_MAXIMO = Decimal("999.9999")
RATIO_MINIMO = Decimal("-999.9999")


class Desviacion(Base):
    __tablename__ = "desviacion"
    __table_args__ = (
        ForeignKeyConstraint(
            ["empresa_id", "periodo_id"],
            ["periodo_seguimiento.empresa_id", "periodo_seguimiento.id"],
            name="fk_desviacion_periodo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_desviacion_cuenta",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "centro_coste_id"],
            ["centro_coste.empresa_id", "centro_coste.id"],
            name="fk_desviacion_centro",
        ),
        # `centro_coste_id` es NULLABLE (D4: las cuentas sin presupuesto se
        # informan con `sin_presupuesto = true` y centro vacio), por lo que la
        # unicidad tambien se resuelve con dos indices parciales.
        Index(
            "uq_desviacion_sin_centro",
            "empresa_id",
            "periodo_id",
            "cuenta_id",
            unique=True,
            sqlite_where=text("centro_coste_id IS NULL"),
            postgresql_where=text("centro_coste_id IS NULL"),
        ),
        Index(
            "uq_desviacion_con_centro",
            "empresa_id",
            "periodo_id",
            "cuenta_id",
            "centro_coste_id",
            unique=True,
            sqlite_where=text("centro_coste_id IS NOT NULL"),
            postgresql_where=text("centro_coste_id IS NOT NULL"),
        ),
        Index("ix_desviacion_empresa_periodo", "empresa_id", "periodo_id"),
        Index("ix_desviacion_empresa_cuenta", "empresa_id", "cuenta_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    periodo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    centro_coste_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    importe_presupuestado: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    importe_real: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    desviacion_absoluta: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    desviacion_relativa: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True
    )
    sin_presupuesto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
