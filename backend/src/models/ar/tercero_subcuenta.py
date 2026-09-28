"""TerceroSubcuenta (SPEC-008): accounting subaccount assigned to a tercero."""

from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    Date,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoSubcuenta(str, enum.Enum):
    CLIENTE = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"


class TerceroSubcuenta(Base):
    __tablename__ = "tercero_subcuenta"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        UniqueConstraint(
            "empresa_id", "tercero_id", "tipo", name="uq_tercero_subcuenta_rol"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    tipo: Mapped[TipoSubcuenta] = mapped_column(
        SqlEnum(TipoSubcuenta, name="tercero_subcuenta_tipo"), nullable=False
    )
    cuenta_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_asignacion: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
