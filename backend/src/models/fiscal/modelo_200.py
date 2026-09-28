from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class Modelo200(Base):
    __tablename__ = "modelo_200"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_modelo_200_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "calculo_is_id",
            name="uq_modelo_200_calculo",
        ),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_modelo_200_empresa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "calculo_is_id"],
            ["calculo_is.empresa_id", "calculo_is.id"],
            name="fk_modelo_200_calculo",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    calculo_is_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    contenido: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    hash_contenido: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
