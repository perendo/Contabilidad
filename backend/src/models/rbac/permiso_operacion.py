"""Closed catalog of business operations, one row per ``(modulo, operacion)``.

The catalog is a seed managed by `services/security/catalogo.py` and the DB
triggers; the API never creates dynamic permissions (deny-by-default: a
permission not granted simply has no row in `matriz_permiso`).

``requiere_datos_contables`` flags operations that mutate accounting data:
every allow/deny over them is audited (FR-005). Plain reads (``ver``) are not
flagged to keep the access log readable (D7 research).
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class OperacionPermiso(str, enum.Enum):
    ver = "ver"
    crear = "crear"
    editar = "editar"
    aprobar = "aprobar"
    importar_exportar = "importar_exportar"
    configurar = "configurar"
    baja = "baja"
    cerrar = "cerrar"


class PermisoOperacion(Base):
    __tablename__ = "permiso_operacion"
    __table_args__ = (
        UniqueConstraint("modulo", "operacion", name="uq_permiso_operacion_modulo_operacion"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    modulo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    operacion: Mapped[OperacionPermiso] = mapped_column(
        SqlEnum(OperacionPermiso, name="permiso_operacion_tipo"), nullable=False
    )
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    requiere_datos_contables: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )