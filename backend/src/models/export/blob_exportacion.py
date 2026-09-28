"""BlobExportacion (SPEC-029 T008): binario del ZIP generado.

El contenido es **inmutable** desde su persistencia (research D9): la
verificacion de integridad (US2) recalcula el SHA-256 sobre estos bytes, de modo
que re-descargar entrega siempre el mismo binario. Se guarda en la misma
transaccion ACID que la cabecera, el manifiesto y el audit log.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class BlobExportacion(Base):
    __tablename__ = "blob_exportacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_blob_exportacion_empresa_id"),
        UniqueConstraint("empresa_id", "exportacion_id", name="uq_blob_exportacion_exportacion"),
        ForeignKeyConstraint(
            ["empresa_id", "exportacion_id"],
            ["exportacion.empresa_id", "exportacion.id"],
            name="fk_blob_exportacion_exportacion",
        ),
        CheckConstraint("tamano_bytes >= 0", name="chk_blob_exportacion_tamano"),
        Index("ix_blob_exportacion_empresa", "empresa_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    exportacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contenido: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
