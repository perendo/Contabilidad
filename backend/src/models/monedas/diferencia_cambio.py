"""DiferenciaCambio (SPEC-016 · US2): valoración a cierre de saldos vivos en divisa.

Una fila por (cuenta, divisa) con saldo vivo distinto de cero al cierre: guarda
el saldo en divisa, el saldo funcional previo, el tipo de cambio de cierre y la
diferencia resultante. El asiento de diferencias se enlaza en ``asiento_id``
(único por valoración: índice ``(empresa, ejercicio, fecha_valoracion)``).
"""

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
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class DiferenciaCambioEstado(str, Enum):
    calculada = "calculada"
    asentada = "asentada"


class DiferenciaCambio(Base):
    __tablename__ = "diferencia_cambio"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_diferencia_empresa_id"),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "fecha_valoracion",
            "cuenta_id",
            "divisa_id",
            name="uq_diferencia_cierre_unica",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_diferencia_cuenta",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "divisa_id"],
            ["moneda.empresa_id", "moneda.id"],
            name="fk_diferencia_moneda",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "tipo_cierre_id"],
            ["tipo_cambio.empresa_id", "tipo_cambio.id"],
            name="fk_diferencia_tipo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "asiento_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_diferencia_asiento",
        ),
        CheckConstraint("diferencia <> 0", name="chk_diferencia_no_nula"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_valoracion: Mapped[date] = mapped_column(Date, nullable=False)
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    divisa_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tipo_cierre_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    saldo_divisa: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    saldo_funcional_previo: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    valoracion: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    diferencia: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estado: Mapped[DiferenciaCambioEstado] = mapped_column(
        SqlEnum(DiferenciaCambioEstado, name="diferencia_cambio_estado"),
        nullable=False,
        default=DiferenciaCambioEstado.asentada,
    )
    asiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)