"""ConfiguracionSII (SPEC-012 T007): enlace SII opcional por empresa (sin envio)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ConfiguracionSII(Base):
    __tablename__ = "configuracion_sii"

    empresa_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    obligatorio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    identificador_emisor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    endpoint_ejecucion: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )