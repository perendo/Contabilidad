"""MovimientoPrevision (SPEC-027 T006): cada flujo colocable en la proyeccion.

Un movimiento proviene de un vencimiento pendiente (SPEC-011/020) o es una
prevision manual del usuario (pago recurrente / cobro estimado, research D3).
`incluido = false` marca los flujos que quedaron fuera de la ultima
proyeccion por no tener fecha prevista, que es el caso limite del spec
("sin fecha quedan fuera de la proyeccion"); `motivo_exclusion` guarda el
codigo (`vencido`, `cobrado`, `anulado`, `sin_fecha`) para que el detalle lo
muestre sin recalcular.

Constitucion III: la FK a `Vencimiento` es **compuesta** `(empresa_id,
vencimiento_id)`, de modo que un vencimiento de otra empresa no puede
enlazarse. Constitucion I: esta tabla no genera asientos, solo proyecta
movimientos ya existentes (plan.md: "no genera asientos nuevos").
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
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


class OrigenMovimientoPrevision(str, Enum):
    vencimiento = "vencimiento"
    remesa_cobro = "remesa_cobro"
    pago_recurrente = "pago_recurrente"
    cobro_estimado = "cobro_estimado"


class TipoMovimientoPrevision(str, Enum):
    cobro = "cobro"
    pago = "pago"


class FrecuenciaMovimiento(str, Enum):
    unico = "unico"
    semanal = "semanal"
    mensual = "mensual"
    anual = "anual"


class MovimientoPrevision(Base):
    __tablename__ = "movimiento_prevision"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_movimiento_prevision_empresa_id"),
        ForeignKeyConstraint(
            ["empresa_id", "prevision_id"],
            ["prevision_tesoreria.empresa_id", "prevision_tesoreria.id"],
            name="fk_movimiento_prevision_prevision",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "vencimiento_id"],
            ["vencimiento.empresa_id", "vencimiento.id"],
            name="fk_movimiento_prevision_vencimiento",
        ),
        CheckConstraint("importe > 0", name="movimiento_prevision_importe_positivo"),
        # Un movimiento excluido siempre explica por que (`sin_fecha`,
        # `vencido`, `cobrado`, `anulado`); uno incluido nunca lleva motivo.
        CheckConstraint(
            "(incluido AND motivo_exclusion IS NULL) OR "
            "(NOT incluido AND motivo_exclusion IS NOT NULL)",
            name="movimiento_prevision_motivo",
        ),
        Index(
            "ix_movimiento_prevision_empresa_prevision",
            "empresa_id",
            "prevision_id",
        ),
        Index(
            "ix_movimiento_prevision_empresa_fecha",
            "empresa_id",
            "fecha_prevista",
        ),
        Index(
            "ix_movimiento_prevision_empresa_vencimiento",
            "empresa_id",
            "vencimiento_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prevision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=True)
    origen: Mapped[OrigenMovimientoPrevision] = mapped_column(
        SqlEnum(OrigenMovimientoPrevision, name="movimiento_prevision_origen"),
        nullable=False,
    )
    vencimiento_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    numero_recibo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tipo: Mapped[TipoMovimientoPrevision] = mapped_column(
        SqlEnum(TipoMovimientoPrevision, name="movimiento_prevision_tipo"),
        nullable=False,
    )
    importe: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    fecha_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    frecuencia: Mapped[FrecuenciaMovimiento] = mapped_column(
        SqlEnum(FrecuenciaMovimiento, name="movimiento_prevision_frecuencia"),
        nullable=False,
        default=FrecuenciaMovimiento.unico,
    )
    concepto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    incluido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    motivo_exclusion: Mapped[str | None] = mapped_column(String(40), nullable=True)
    orden_repeticion: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
