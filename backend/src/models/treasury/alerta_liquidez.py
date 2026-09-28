"""AlertaLiquidez (SPEC-027 T007): aviso de saldo proyectado negativo.

research.md D6: al generar la prevision se recorre cada bucket y se crea una
alerta para todo `saldo_acumulado < 0`. El saldo exactamente cero NO genera
alerta (edge case del spec: "se muestra como limite de solvencia").

`importe_deficit` es el valor absoluto del saldo negativo y `accion_sugerida`
orienta al usuario (reprogramar un pago o incorporar un ingreso previsto).
Una sola alerta por `(empresa_id, prevision_id, fecha)`: una alerta por bucket.
Constitucion III: FKs compuestas por `empresa_id`.
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


class EstadoAlertaLiquidez(str, Enum):
    abierta = "abierta"
    atendida = "atendida"
    ignorada = "ignorada"


class AccionSugeridaLiquidez(str, Enum):
    reprogramar_pago = "reprogramar_pago"
    incluir_ingreso = "incluir_ingreso"


class AlertaLiquidez(Base):
    __tablename__ = "alerta_liquidez"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_alerta_liquidez_empresa_id"),
        UniqueConstraint(
            "empresa_id",
            "prevision_id",
            "fecha",
            name="uq_alerta_liquidez_prevision_fecha",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "prevision_id"],
            ["prevision_tesoreria.empresa_id", "prevision_tesoreria.id"],
            name="fk_alerta_liquidez_prevision",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "movimiento_origen_id"],
            ["movimiento_prevision.empresa_id", "movimiento_prevision.id"],
            name="fk_alerta_liquidez_movimiento",
        ),
        CheckConstraint("saldo_proyectado < 0", name="alerta_liquidez_saldo_negativo"),
        CheckConstraint("importe_deficit > 0", name="alerta_liquidez_deficit_positivo"),
        Index("ix_alerta_liquidez_empresa_prevision", "empresa_id", "prevision_id"),
        Index("ix_alerta_liquidez_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prevision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    saldo_proyectado: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    importe_deficit: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    estado: Mapped[EstadoAlertaLiquidez] = mapped_column(
        SqlEnum(EstadoAlertaLiquidez, name="alerta_liquidez_estado"),
        nullable=False,
        default=EstadoAlertaLiquidez.abierta,
    )
    accion_sugerida: Mapped[AccionSugeridaLiquidez] = mapped_column(
        SqlEnum(AccionSugeridaLiquidez, name="alerta_liquidez_accion"),
        nullable=False,
        default=AccionSugeridaLiquidez.reprogramar_pago,
    )
    movimiento_origen_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    atendida_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fecha_atencion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
