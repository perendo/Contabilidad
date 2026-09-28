"""LibroOficial y Legalizacion models (SPEC-019 US2).

`libro_oficial` es el PDF inmutable de los libros de un ejercicio cerrado
(FR-005); `sha256` es la huella del contenido canonico textual (no del binario
PDF, D3/D4). `legalizacion` certifica la integridad (FR-006): una vigente
(`valido = true`) refuerza el bloqueo de SPEC-004 (FR-007). Re-emision solo con
huella identica (409 en otro caso).
"""

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
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class LibroTipo(str, Enum):
    diario = "diario"
    mayor = "mayor"
    cuentas_anuales = "cuentas_anuales"


class LibroOficial(Base):
    __tablename__ = "libro_oficial"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_libro_oficial_empresa_id"),
        UniqueConstraint(
            "empresa_id", "ejercicio", "tipo", name="uq_libro_oficial_empresa_ejercicio_tipo"
        ),
        Index("ix_libro_oficial_empresa", "empresa_id"),
        Index("ix_libro_oficial_empresa_ejercicio", "empresa_id", "ejercicio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ejercicio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tipo: Mapped[LibroTipo] = mapped_column(
        SqlEnum(LibroTipo, name="libro_tipo"), nullable=False
    )
    periodo_desde: Mapped[date] = mapped_column(Date, nullable=False)
    periodo_hasta: Mapped[date] = mapped_column(Date, nullable=False)
    contenido_pdf: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Legalizacion(Base):
    __tablename__ = "legalizacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_legalizacion_empresa_id"),
        UniqueConstraint("empresa_id", "ejercicio", name="uq_legalizacion_empresa_ejercicio"),
        CheckConstraint(
            "rango_asientos_hasta >= rango_asientos_desde",
            name="chk_legalizacion_rango",
        ),
        Index("ix_legalizacion_empresa", "empresa_id"),
        Index("ix_legalizacion_empresa_ejercicio", "empresa_id", "ejercicio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ejercicio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rango_asientos_desde: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rango_asientos_hasta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_asientos: Mapped[int] = mapped_column(Integer, nullable=False)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    fichero: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    fecha_emision: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_legalizacion: Mapped[date | None] = mapped_column(Date, nullable=True)
    valido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    motivo_reemision: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )