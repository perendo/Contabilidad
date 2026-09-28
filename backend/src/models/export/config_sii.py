"""ConfigSii (SPEC-029 T005): configuracion por empresa para el enlace SII.

Research D8: la presentacion telematica a la AEAT queda **fuera de alcance**.
Este modelo solo declara si la empresa esta obligada, si esta exenta de anexos y
su clave de regimen (01-17 del modelo 303), que es lo que el bloque
`datos_sii/` necesita para preparar el fichero de subida manual.

Convive con `models.fiscal.configuracion_sii.ConfiguracionSII` (SPEC-012), que
guarda la configuracion tecnica de envio (endpoint, identificador de emisor).
`services.export.sii.config_efectiva` resuelve primero esta tabla y cae a la de
SPEC-012 cuando la empresa no tiene alta aqui.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ConfigSii(Base):
    __tablename__ = "config_sii"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_config_sii_empresa_id"),
        # Una sola configuracion SII por empresa (data-model).
        UniqueConstraint("empresa_id", name="uq_config_sii_empresa"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    obligado_sii: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sin_anexo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    clave_regimen: Mapped[str | None] = mapped_column(String(10), nullable=True)
    entidad_representante_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    fecha_alta: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
