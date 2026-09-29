"""MandatoSepa model: mandato de domiciliación (obligatorio B2B, recomendable CORE)."""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum

from sqlalchemy import BigInteger, Date, String, UniqueConstraint, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base
from models.treasury.remesa import TipoAdeudo


class MandatoEstado(str, Enum):
    firmado = "firmado"
    caducado = "caducado"
    revocado = "revocado"


class MandatoSepa(Base):
    __tablename__ = "mandato_sepa"
    __table_args__ = (
        # Nombre explicito, por la colision con el `("empresa_id", "id")` de abajo: la
        # convencion usa solo la primera columna y aqui las dos empiezan por
        # `empresa_id`. Ver `devolucion.py` y el guard
        # `test_no_hay_dos_restricciones_con_el_mismo_nombre`.
        UniqueConstraint(
            "empresa_id", "tercero_id", "mandato_ref",
            name="uq_mandato_sepa_empresa_tercero_ref",
        ),
        UniqueConstraint("empresa_id", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    mandato_ref: Mapped[str] = mapped_column(String(35), nullable=False)
    fecha_firma: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[TipoAdeudo] = mapped_column(
        SqlEnum(TipoAdeudo, name="tipo_adeudo"), nullable=False
    )
    estado: Mapped[MandatoEstado] = mapped_column(
        SqlEnum(MandatoEstado, name="mandato_estado"), nullable=False
    )