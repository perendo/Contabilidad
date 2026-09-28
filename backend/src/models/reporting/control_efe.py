"""ClasificacionEfe (SPEC-010 T027): reasignacion manual de actividad en el EFE.

El EFE clasifica por defecto los movimientos de tesoreria (grupo 5) segun la
contrapartida; esta tabla permite fijar manualmente la actividad de un
movimiento (linea del diario) antes de formular. Multi-tenant por ``empresa_id``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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
from models.reporting.configuracion import ActividadEfe


class ClasificacionEfe(Base):
    __tablename__ = "clasificacion_efe"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_clasificacion_efe_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "linea_id",
            name="uq_clasificacion_efe_linea",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    linea_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    actividad: Mapped[ActividadEfe] = mapped_column(
        SqlEnum(ActividadEfe, name="actividad_efe"), nullable=False
    )
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )