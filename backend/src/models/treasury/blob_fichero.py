"""BlobFichero model: ficheros de domiciliación generados y R19/C19 recibidos."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    DateTime,
    LargeBinary,
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


class TipoBlob(str, Enum):
    remesa_sepa = "remesa_sepa"
    remesa_csb1919 = "remesa_csb1919"
    r19 = "r19"
    c19 = "c19"


class BlobFichero(Base):
    __tablename__ = "blob_fichero"
    __table_args__ = (UniqueConstraint("empresa_id", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tipo: Mapped[TipoBlob] = mapped_column(
        SqlEnum(TipoBlob, name="tipo_blob"), nullable=False
    )
    contenido: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )