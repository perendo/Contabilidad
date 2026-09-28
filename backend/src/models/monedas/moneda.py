"""Moneda (SPEC-016 · US1): moneda funcional y divisas de trabajo por empresa.

La moneda funcional es única por empresa (índice parcial) y se crea por defecto
en EUR. Las divisas de trabajo comparten tabla con ``es_funcional = false``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base

_CODIGO_ISO_CHK = "codigo_iso GLOB '[A-Z][A-Z][A-Z]' AND length(codigo_iso) = 3"


class Moneda(Base):
    __tablename__ = "moneda"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_moneda_empresa_id"),
        CheckConstraint(_CODIGO_ISO_CHK, name="chk_moneda_codigo_iso"),
        Index(
            "ix_moneda_funcional_unica",
            "empresa_id",
            unique=True,
            sqlite_where=text("es_funcional = 1"),
            postgresql_where=text("es_funcional = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codigo_iso: Mapped[str] = mapped_column(String(3), nullable=False)
    es_funcional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)