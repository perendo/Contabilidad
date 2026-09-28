"""Cabecera de version del plan de cuentas con vigencia por empresa (SPEC-025)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoVersion(str, Enum):
    borrador = "borrador"
    vigente = "vigente"
    anulada = "anulada"


class CatalogoVersion(Base):
    __tablename__ = "catalogo_version"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_catalogo_version_empresa_id"),
        UniqueConstraint(
            "empresa_id", "numero_version", name="uq_catalogo_version_empresa_numero"
        ),
        CheckConstraint(
            "fecha_fin IS NULL OR fecha_fin >= fecha_inicio",
            name="chk_catalogo_version_rango",
        ),
        ForeignKeyConstraint(
            ["empresa_id"], ["companies.company_id"], name="fk_catalogo_version_empresa"
        ),
        Index("ix_catalogo_version_empresa", "empresa_id"),
        Index(
            "ix_catalogo_version_empresa_vigencia",
            "empresa_id",
            "fecha_inicio",
            "fecha_fin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    numero_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoVersion] = mapped_column(
        SqlEnum(EstadoVersion, name="catalogo_version_estado"),
        nullable=False,
        default=EstadoVersion.borrador,
    )
    es_migracion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
