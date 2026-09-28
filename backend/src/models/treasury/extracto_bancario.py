"""ExtractoBancario (SPEC-013): cabecera del fichero de extracto importado."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ExtractoEstado(str, enum.Enum):
    importado = "importado"
    duplicado = "duplicado"


class ExtractoBancario(Base):
    __tablename__ = "extracto_bancario"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        UniqueConstraint("empresa_id", "sha256", name="uq_extracto_empresa_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    saldo_inicial: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    saldo_final: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    nombre_fichero: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[ExtractoEstado] = mapped_column(
        SqlEnum(ExtractoEstado, name="extracto_estado"),
        nullable=False,
        default=ExtractoEstado.importado,
    )
    n_movimientos: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_importacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    creado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
