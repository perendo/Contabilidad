"""CuentaBancaria model: cuentas bancarias vinculadas a la empresa activa."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class CuentaBancaria(Base):
    __tablename__ = "cuentas_bancarias"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_cuentas_bancarias_empresa_id"),
        UniqueConstraint("empresa_id", "iban", name="uq_cuentas_bancarias_empresa_iban"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    banco: Mapped[str | None] = mapped_column(String(120), nullable=True)
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    cuenta_contable: Mapped[str] = mapped_column(String(20), nullable=False, default="572")
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
