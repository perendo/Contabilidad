"""Mapeo de cuentas entre dos versiones del catalogo (SPEC-025)."""

from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoMovimiento(str, Enum):
    igual = "igual"
    renombrada = "renombrada"
    suprimida = "suprimida"
    nueva = "nueva"


class OrigenMapeo(str, Enum):
    manifiesto = "manifiesto"
    autogenerado = "autogenerado"


class MapeoCuenta(Base):
    __tablename__ = "mapeo_cuenta"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_mapeo_cuenta_empresa_id"),
        UniqueConstraint(
            "empresa_id",
            "version_origen_id",
            "version_destino_id",
            "cuenta_origen_id",
            name="uq_mapeo_cuenta_clave",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "version_origen_id"],
            ["catalogo_version.empresa_id", "catalogo_version.id"],
            name="fk_mapeo_cuenta_version_origen",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "version_destino_id"],
            ["catalogo_version.empresa_id", "catalogo_version.id"],
            name="fk_mapeo_cuenta_version_destino",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_origen_id"],
            ["catalogo_cuenta.empresa_id", "catalogo_cuenta.id"],
            name="fk_mapeo_cuenta_origen",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_destino_id"],
            ["catalogo_cuenta.empresa_id", "catalogo_cuenta.id"],
            name="fk_mapeo_cuenta_destino",
        ),
        Index("ix_mapeo_cuenta_empresa_destino", "empresa_id", "version_destino_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version_origen_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version_destino_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cuenta_origen_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    cuenta_destino_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    tipo_movimiento: Mapped[TipoMovimiento] = mapped_column(
        SqlEnum(TipoMovimiento, name="mapeo_tipo_movimiento"),
        nullable=False,
        default=TipoMovimiento.igual,
    )
    requiere_reclasificacion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    origen: Mapped[OrigenMapeo] = mapped_column(
        SqlEnum(OrigenMapeo, name="mapeo_origen"),
        nullable=False,
        default=OrigenMapeo.manifiesto,
    )
