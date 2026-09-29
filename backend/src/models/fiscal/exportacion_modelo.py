"""ExportacionModelo (SPEC-012 T006): exportacion trazable de un modelo fiscal."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ModeloFiscal(str, enum.Enum):
    m303 = "303"
    m347 = "347"
    m349 = "349"


class EstadoExportacion(str, enum.Enum):
    generado = "generado"
    regenerado = "regenerado"
    anulado = "anulado"


class ExportacionModelo(Base):
    __tablename__ = "exportacion_modelo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_exportacion_modelo_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "modelo",
            "numero_exportacion",
            name="uq_exportacion_modelo_numero",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    modelo: Mapped[ModeloFiscal] = mapped_column(
        SqlEnum(ModeloFiscal, name="modelo_fiscal"), nullable=False
    )
    numero_exportacion: Mapped[int] = mapped_column(BigInteger, nullable=False)
    periodo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    formato: Mapped[str] = mapped_column(String(10), nullable=False, default="csv")
    fecha_exportacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    usuario_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contenido_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fichero_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    estado: Mapped[EstadoExportacion] = mapped_column(
        # Sufijo por la misma razon que en `periodo_fiscal`: `models.export` ya usa
        # `estado_exportacion` para los estados de una exportacion integral
        # ('en_proceso', 'lista', 'fallida'), que no son estos. En PostgreSQL un
        # tipo se define una vez y en SQLite no hay ENUM, asi que la colision solo
        # aparece al escribir la migracion. Guard:
        # `test_no_hay_dos_enums_con_el_mismo_nombre_y_valores_distintos`.
        SqlEnum(EstadoExportacion, name="estado_exportacion_modelo"),
        nullable=False,
        default=EstadoExportacion.generado,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )