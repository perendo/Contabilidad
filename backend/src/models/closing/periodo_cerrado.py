"""PeriodoCerrado (SPEC-028 T005): estado de cierre de un periodo intermedio.

La fila se crea **al cerrar** el periodo (research D2 descarta la tabla de
calendario con 80 filas por empresa): un periodo sin fila esta abierto. El
enum de estado conserva la transicion completa
``abierto -> cerrado -> reabierto_ajuste -> cerrado_ajustado``; el estado
`cerrado_ajustado` puede reabrirse de nuevo con una nueva solicitud
(incrementando `n_reaperturas`).

Solo los estados `cerrado` y `cerrado_ajustado` bloquean la contabilizacion:
un periodo en `reabierto_ajuste` esta deliberadamente abierto para que el
asiento de rectificacion se pueda asentar (constitucion II).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
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


class TipoPeriodo(str, Enum):
    MES = "MES"
    TRIMESTRE = "TRIMESTRE"


class EstadoPeriodo(str, Enum):
    abierto = "abierto"
    cerrado = "cerrado"
    reabierto_ajuste = "reabierto_ajuste"
    cerrado_ajustado = "cerrado_ajustado"


#: Estados que bloquean nuevas contabilizaciones en el rango del periodo.
ESTADOS_BLOQUEANTES: frozenset[EstadoPeriodo] = frozenset(
    {EstadoPeriodo.cerrado, EstadoPeriodo.cerrado_ajustado}
)


class PeriodoCerrado(Base):
    __tablename__ = "periodo_cerrado"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_periodo_cerrado_empresa_id"),
        # Clave natural del data-model: un solo registro por periodo y empresa.
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "tipo",
            "periodo",
            name="uq_periodo_cerrado_natural",
        ),
        CheckConstraint("periodo >= 1 AND periodo <= 12", name="chk_periodo_cerrado_periodo"),
        CheckConstraint("n_reaperturas >= 0", name="chk_periodo_cerrado_reaperturas"),
        CheckConstraint("fecha_fin >= fecha_ini", name="chk_periodo_cerrado_rango"),
        Index("ix_periodo_cerrado_empresa_ejercicio", "empresa_id", "ejercicio"),
        Index("ix_periodo_cerrado_empresa_estado", "empresa_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[TipoPeriodo] = mapped_column(
        SqlEnum(TipoPeriodo, name="tipo_periodo"), nullable=False
    )
    periodo: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_ini: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoPeriodo] = mapped_column(
        SqlEnum(EstadoPeriodo, name="estado_periodo"),
        nullable=False,
        default=EstadoPeriodo.cerrado,
    )
    cerrado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cerrado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    balanza_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    n_reaperturas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
