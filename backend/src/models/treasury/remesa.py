"""Remesa model: agrupación de recibos para domiciliación.

Numeración correlativa por (empresa_id, ejercicio); todos los filtros y
claves incluyen empresa_id (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class FormatoRemesa(str, Enum):
    SEPA_DD = "SEPA_DD"
    CSB_19_19 = "CSB_19_19"


class TipoAdeudo(str, Enum):
    CORE = "CORE"
    B2B = "B2B"


class RemesaEstado(str, Enum):
    borrador = "borrador"
    emitida = "emitida"
    cobrada = "cobrada"
    devuelta = "devuelta"


class Remesa(Base):
    __tablename__ = "remesa"
    __table_args__ = (
        # Nombre explicito, por la colision con el `("empresa_id", "id")` de abajo. La
        # correlatividad de remesas (sin saltos por empresa y ejercicio) es
        # `ejercicio` + `numero_remesa`; el `("empresa_id", "id")` existe para que las
        # FKs compuestas de `recibo_remesa` puedan apuntar aqui. Ver `devolucion.py`.
        UniqueConstraint(
            "empresa_id", "ejercicio", "numero_remesa",
            name="uq_remesa_empresa_ejercicio_numero",
        ),
        UniqueConstraint("empresa_id", "id"),
        CheckConstraint("importe_total > 0", name="importe_total_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_remesa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha_emision: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_cargo: Mapped[date | None] = mapped_column(Date, nullable=True)
    formato: Mapped[FormatoRemesa] = mapped_column(
        SqlEnum(FormatoRemesa, name="formato_remesa"), nullable=False
    )
    tipo_adeudo: Mapped[TipoAdeudo] = mapped_column(
        SqlEnum(TipoAdeudo, name="tipo_adeudo"), nullable=False
    )
    importe_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estado: Mapped[RemesaEstado] = mapped_column(
        SqlEnum(RemesaEstado, name="remesa_estado"), nullable=False
    )
    fichero_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )