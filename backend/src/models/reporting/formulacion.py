"""FormulacionCuentasAnuales (SPEC-010 T033): documento oficial inmutable.

Sella (snapshot JSONB + sha256) el Balance, la PyG y el EFE de un ejercicio
cerrado. La reformulacion exige anular antes; el historico nunca se borra
(constitucion II). ``numero_formulacion`` es correlativo por (empresa, ejercicio).
"""

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


class FormulacionEstado(str, enum.Enum):
    formulada = "formulada"
    anulada = "anulada"


class FormulacionCuentasAnuales(Base):
    __tablename__ = "formulacion_cuentas_anuales"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_formulacion_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "numero_formulacion",
            name="uq_formulacion_numero",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    numero_formulacion: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha_formulacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    usuario_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contenido_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[FormulacionEstado] = mapped_column(
        SqlEnum(FormulacionEstado, name="formulacion_estado"),
        nullable=False,
        default=FormulacionEstado.formulada,
    )
    motivo_anulacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    anulada_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    anulada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    observaciones: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )