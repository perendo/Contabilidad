"""Subvencion model (SPEC-019 US1): control de gasto subvencionado por empresa.

Multi-tenant estricto (constitucion III): PK compuesta efectiva `(empresa_id,
id)` con unico por `(empresa_id, id)`. La imputacion de gastos a nivel de linea
se valida en `services/ngo/justificacion.py` en la misma transaccion ACID; la
percepcion de la subvencion se asienta fuera de esta feature (solo control de
gasto). Importes con `Decimal` (FR-010), prohibido float.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
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


class SubvencionEstado(str, Enum):
    concedida = "concedida"
    en_curso = "en_curso"
    justificada = "justificada"
    reintegrada = "reintegrada"


class Subvencion(Base):
    __tablename__ = "subvencion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_subvencion_empresa_id"),
        CheckConstraint("importe_concedido > 0", name="chk_subvencion_importe_positivo"),
        Index("ix_subvencion_empresa", "empresa_id"),
        Index("ix_subvencion_empresa_estado", "empresa_id", "estado", "ejercicio"),
        Index("ix_subvencion_empresa_referencia", "empresa_id", "referencia"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entidad_concedente: Mapped[str] = mapped_column(String(120), nullable=False)
    programa: Mapped[str] = mapped_column(String(120), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(40), nullable=True)
    importe_concedido: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    ejercicio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    estado: Mapped[SubvencionEstado] = mapped_column(
        SqlEnum(SubvencionEstado, name="subvencion_estado"),
        nullable=False,
        default=SubvencionEstado.concedida,
    )
    partidas: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )