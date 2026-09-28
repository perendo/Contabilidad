"""ReciboRemesa model: línea de remesa que referencia el vencimiento a domiciliar."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class ReciboEstado(str, Enum):
    pendiente = "pendiente"
    remesado = "remesado"
    cobrado = "cobrado"
    devuelto = "devuelto"


class ReciboRemesa(Base):
    __tablename__ = "recibo_remesa"
    __table_args__ = (
        UniqueConstraint("empresa_id", "remesa_id", "vencimiento_id"),
        Index(
            "uq_recibo_remesa_empresa_vencimiento",
            "empresa_id",
            "vencimiento_id",
            unique=True,
            postgresql_where=text("estado != 'devuelto'"),
            sqlite_where=text("estado != 'devuelto'"),
        ),
        UniqueConstraint("empresa_id", "id"),
        ForeignKeyConstraint(
            ["empresa_id", "remesa_id"],
            ["remesa.empresa_id", "remesa.id"],
            name="fk_recibo_remesa_empresa_remesa",
        ),
        CheckConstraint("importe > 0", name="importe_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    remesa_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    vencimiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    recibo_num: Mapped[str] = mapped_column(String(32), nullable=False)
    tercero_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fecha_cargo: Mapped[date] = mapped_column(Date, nullable=False)
    descuento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estado: Mapped[ReciboEstado] = mapped_column(
        SqlEnum(ReciboEstado, name="recibo_estado"), nullable=False
    )
    asiento_cobro_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    fecha_cobro: Mapped[date | None] = mapped_column(Date, nullable=True)