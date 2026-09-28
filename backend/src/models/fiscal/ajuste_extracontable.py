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
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoAjusteExtracontable(str, Enum):
    AJUSTE_POSITIVO = "AJUSTE_POSITIVO"
    AJUSTE_NEGATIVO = "AJUSTE_NEGATIVO"
    DEDUCCION = "DEDUCCION"
    BONIFICACION = "BONIFICACION"


class AjusteExtracontable(Base):
    __tablename__ = "ajuste_extracontable"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "id", name="uq_ajuste_extracontable_tenant_id"
        ),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_ajuste_extracontable_empresa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "calculo_is_id"],
            ["calculo_is.empresa_id", "calculo_is.id"],
            name="fk_ajuste_extracontable_calculo",
        ),
        CheckConstraint("importe > 0", name="chk_ajuste_extracontable_importe"),
        Index(
            "ix_ajuste_extracontable_empresa_calculo",
            "empresa_id",
            "calculo_is_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    calculo_is_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tipo: Mapped[TipoAjusteExtracontable] = mapped_column(
        SqlEnum(TipoAjusteExtracontable, name="tipo_ajuste_extracontable"),
        nullable=False,
    )
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False)
    referencia_normativa: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
