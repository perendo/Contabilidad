"""PrevisionTesoreria (SPEC-027 T005): cabecera de la proyeccion de flujos.

research.md D2: la prevision agrupa los `MovimientoPrevision` por la
granularidad elegida (dia/semana/mes) y arrastra el saldo acumulado de
`saldo_inicial + S(movimientos hasta k)`. La cabecera guarda el rango, la
granularidad y los saldos de arranque y cierre del periodo proyectado.

Constitucion III: `empresa_id` en la unicidad compuesta, en el indice de
correlatividad y derivado siempre de la sesion. Constitucion IV:
`numero_prevision` es unico y correlativo por empresa. Importes en
`NUMERIC(18,4)` / `Decimal` (prohibido `float`).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class GranularidadPrevision(str, Enum):
    dia = "dia"
    semana = "semana"
    mes = "mes"


class EstadoPrevision(str, Enum):
    borrador = "borrador"
    generada = "generada"
    anulada = "anulada"


class PrevisionTesoreria(Base):
    __tablename__ = "prevision_tesoreria"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_prevision_tesoreria_empresa_id"),
        # Constitucion IV: correlatividad por empresa, sin saltos ni duplicados.
        UniqueConstraint(
            "empresa_id",
            "numero_prevision",
            name="uq_prevision_tesoreria_numero",
        ),
        CheckConstraint("hasta_fecha >= desde_fecha", name="prevision_rango_fechas"),
        CheckConstraint("numero_prevision > 0", name="prevision_numero_positivo"),
        ForeignKeyConstraint(
            ["empresa_id"],
            ["companies.company_id"],
            name="fk_prevision_tesoreria_empresa",
        ),
        Index("ix_prevision_tesoreria_empresa_fecha", "empresa_id", "desde_fecha"),
        Index("ix_prevision_tesoreria_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    numero_prevision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    desde_fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hasta_fecha: Mapped[date] = mapped_column(Date, nullable=False)
    granularidad: Mapped[GranularidadPrevision] = mapped_column(
        SqlEnum(GranularidadPrevision, name="prevision_granularidad"), nullable=False
    )
    saldo_inicial: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    saldo_final: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0)
    )
    origen_saldo_inicial: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: Definiciones manuales del plan (pago recurrente / cobro estimado) tal y
    #: como las declaro el usuario. Es la **definicion** del plan, no su recorte
    #: temporal: al regenerar con otro rango se re-expande desde aqui, de modo
    #: que un pago mensual siga cubriendo los meses nuevos y una reprogramacion
    #: (alerta de liquidez) se conserve.
    plan_manual: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    estado: Mapped[EstadoPrevision] = mapped_column(
        SqlEnum(EstadoPrevision, name="prevision_estado"),
        nullable=False,
        default=EstadoPrevision.generada,
    )
    creado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def ejercicio(self) -> int:
        """Ejercicio contable de arranque de la proyeccion."""
        return self.desde_fecha.year
