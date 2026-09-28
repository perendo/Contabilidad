from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class Modelo115(Base):
    __tablename__ = "modelo_115"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_modelo_115_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "liquidacion_retenciones_id",
            name="uq_modelo_115_liquidacion",
        ),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "trimestre",
            name="uq_modelo_115_ejercicio_trimestre",
        ),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_modelo_115_empresa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "liquidacion_retenciones_id"],
            [
                "liquidacion_retenciones.empresa_id",
                "liquidacion_retenciones.id",
            ],
            name="fk_modelo_115_liquidacion",
        ),
        CheckConstraint("trimestre BETWEEN 1 AND 4", name="chk_modelo_115_trimestre"),
        CheckConstraint("length(hash_contenido) = 64", name="chk_modelo_115_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    liquidacion_retenciones_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False
    )
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    trimestre: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    contenido: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    hash_contenido: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
