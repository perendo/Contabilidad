"""AlertaConciliacion (SPEC-013): aviso de operaciones sin correspondencia."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class TipoAlerta(str, enum.Enum):
    movimiento_sin_apunte = "movimiento_sin_apunte"
    apunte_sin_extracto = "apunte_sin_extracto"
    importe_concepto_dudoso = "importe_concepto_dudoso"


class EstadoAlerta(str, enum.Enum):
    abierta = "abierta"
    resuelta = "resuelta"


class AlertaConciliacion(Base):
    __tablename__ = "alerta_conciliacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id"),
        ForeignKeyConstraint(
            ["empresa_id", "conciliacion_id"],
            ["conciliacion.empresa_id", "conciliacion.id"],
            name="fk_alerta_empresa_conciliacion",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    conciliacion_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    tipo: Mapped[TipoAlerta] = mapped_column(
        SqlEnum(TipoAlerta, name="alerta_tipo"), nullable=False
    )
    movimiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[EstadoAlerta] = mapped_column(
        SqlEnum(EstadoAlerta, name="alerta_estado"),
        nullable=False,
        default=EstadoAlerta.abierta,
    )
