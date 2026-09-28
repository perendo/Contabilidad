"""Proyeccion de membresia y estado de cada cuenta en una version (SPEC-025)."""

from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class EstadoCuentaVersion(str, Enum):
    igual = "igual"
    nueva = "nueva"
    renombrada = "renombrada"
    suprimida = "suprimida"


class CatalogoCuenta(Base):
    __tablename__ = "catalogo_cuenta"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_catalogo_cuenta_empresa_id"),
        UniqueConstraint(
            "empresa_id",
            "version_id",
            "account_id",
            name="uq_catalogo_cuenta_version_account",
        ),
        UniqueConstraint(
            "empresa_id",
            "version_id",
            "codigo_version",
            name="uq_catalogo_cuenta_version_codigo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "version_id"],
            ["catalogo_version.empresa_id", "catalogo_version.id"],
            name="fk_catalogo_cuenta_version",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "account_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_catalogo_cuenta_account",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "parent_version_id"],
            ["catalogo_cuenta.empresa_id", "catalogo_cuenta.id"],
            name="fk_catalogo_cuenta_parent",
        ),
        Index("ix_catalogo_cuenta_empresa_version", "empresa_id", "version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codigo_version: Mapped[str] = mapped_column(String(8), nullable=False)
    nombre_version: Mapped[str] = mapped_column(String(200), nullable=False)
    estado: Mapped[EstadoCuentaVersion] = mapped_column(
        SqlEnum(EstadoCuentaVersion, name="catalogo_cuenta_estado"),
        nullable=False,
        default=EstadoCuentaVersion.igual,
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
