"""Manifiesto de la exportacion (SPEC-029 T007): inventario de bloques.

`ManifiestoExportacion` es la cabecera (un unico manifiesto por exportacion) y
`ManifiestoBloque` una linea por bloque de datos con su conteo, huella y rango
de ejercicios/fechas. Ambas son **append-only** (constitution II): el manifiesto
es parte de la evidencia de integridad, no un registro editable.

`sha256_fichero` es el SHA-256 del **binario completo del ZIP** y vive en la
base de datos, no dentro del propio ZIP: un fichero no puede contener su propio
hash. El `manifest.json` interior lleva `sha256_contenido`, el digest del
contenido de los bloques (research D6, desvio documentado en el tasks.md).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base

#: Version del formato de `manifest.json` y de los ficheros por bloque.
FORMATO_VERSION: str = "1.0.0"


class ManifiestoExportacion(Base):
    __tablename__ = "manifiesto_exportacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_manifiesto_exportacion_empresa_id"),
        UniqueConstraint(
            "empresa_id", "exportacion_id", name="uq_manifiesto_exportacion_exportacion"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "exportacion_id"],
            ["exportacion.empresa_id", "exportacion.id"],
            name="fk_manifiesto_exportacion_exportacion",
        ),
        Index("ix_manifiesto_exportacion_empresa", "empresa_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    exportacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    formato_version: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Redundante con `empresa_id` a proposito: permite verificar la tension
    #: `tenant_id == empresa_id` desde el JSON interior sin tocar la cabecera
    #: (research D4/D6).
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    n_bloques: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256_fichero: Mapped[str] = mapped_column(String(64), nullable=False)


class ManifiestoBloque(Base):
    __tablename__ = "manifiesto_bloque"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_manifiesto_bloque_empresa_id"),
        ForeignKeyConstraint(
            ["empresa_id", "manifiesto_id"],
            ["manifiesto_exportacion.empresa_id", "manifiesto_exportacion.id"],
            name="fk_manifiesto_bloque_manifiesto",
        ),
        CheckConstraint("conteo_registros >= 0", name="chk_manifiesto_bloque_conteo"),
        Index("ix_manifiesto_bloque_manifiesto", "empresa_id", "manifiesto_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifiesto_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    bloque: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Snapshot CSV de las entidades incluidas, p. ej. `"journal_entry,tercero"`.
    entidades_exportadas: Mapped[str] = mapped_column(String(100), nullable=False)
    conteo_registros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fecha_min: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_max: Mapped[date | None] = mapped_column(Date, nullable=True)
    ejercicio_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ejercicio_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
