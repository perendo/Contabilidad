"""Tercero master entity (SPEC-008): clients and providers per company.

Extended from the SPEC-020 minimal scaffold (nombre/nif/iban/bic kept as-is
for SEPA headers); adds roles, contact, NIF uniqueness per company and
soft-deactivation. ``nombre`` is the razón social (deviation documented).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class Tercero(Base):
    __tablename__ = "tercero"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        UniqueConstraint("empresa_id", "nif", name="uq_tercero_empresa_nif"),
        CheckConstraint(
            "es_cliente IS TRUE OR es_proveedor IS TRUE",
            name="chk_tercero_al_menos_un_rol",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    nif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    es_cliente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    es_proveedor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    direcciones: Mapped[list | None] = mapped_column(JSON, nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    correo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    banco: Mapped[str | None] = mapped_column(String(120), nullable=True)
    autofactura: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)