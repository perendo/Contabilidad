"""CentroCoste model (SPEC-017 US1): jerarquía de centros analíticos por empresa.

Multi-tenant estricto (constitución III): PK compuesta efectiva
`(empresa_id, id)` y unicidad por `(empresa_id, codigo)`. El árbol usa
`parent_id` simple con validación de ciclo en app y la closure table
`jerarquia_centro` materializa los pares ancestro→descendiente. Los centros con
imputaciones o descendientes NO se borran físicamente (solo inactivación).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
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


class CentroTipo(str, Enum):
    departamento = "departamento"
    proyecto = "proyecto"
    subvencion = "subvencion"
    delegacion = "delegacion"


class CentroEstado(str, Enum):
    activo = "activo"
    inactivo = "inactivo"


class CentroCoste(Base):
    __tablename__ = "centro_coste"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_centro_coste_empresa_id"),
        UniqueConstraint("empresa_id", "codigo", name="uq_centro_coste_empresa_codigo"),
        CheckConstraint(
            "length(codigo) BETWEEN 1 AND 20", name="chk_centro_coste_codigo_len"
        ),
        CheckConstraint(
            "length(nombre) BETWEEN 1 AND 120", name="chk_centro_coste_nombre_len"
        ),
        CheckConstraint(
            "parent_id <> id", name="chk_centro_coste_no_auto_raiz"
        ),
        ForeignKeyConstraint(
            ["empresa_id", "parent_id"],
            ["centro_coste.empresa_id", "centro_coste.id"],
            name="fk_centro_coste_parent",
        ),
        Index("ix_centro_coste_empresa", "empresa_id"),
        Index("ix_centro_coste_empresa_parent", "empresa_id", "parent_id"),
        Index("ix_centro_coste_empresa_tipo", "empresa_id", "tipo", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[CentroTipo] = mapped_column(
        SqlEnum(CentroTipo, name="centro_tipo"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    subvencion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estado: Mapped[CentroEstado] = mapped_column(
        SqlEnum(CentroEstado, name="centro_estado"),
        nullable=False,
        default=CentroEstado.activo,
    )
    es_hoja: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )