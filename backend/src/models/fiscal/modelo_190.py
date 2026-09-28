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


class Modelo190(Base):
    __tablename__ = "modelo_190"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_modelo_190_retenciones_tenant_id"),
        UniqueConstraint(
            "empresa_id", "ejercicio", name="uq_modelo_190_ejercicio"
        ),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_modelo_190_retenciones_empresa",
        ),
        CheckConstraint(
            "n_perceptores >= 0", name="chk_modelo_190_perceptores"
        ),
        CheckConstraint(
            "length(hash_contenido) = 64", name="chk_modelo_190_hash"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    contenido: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    hash_contenido: Mapped[str] = mapped_column(String(64), nullable=False)
    n_perceptores: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
