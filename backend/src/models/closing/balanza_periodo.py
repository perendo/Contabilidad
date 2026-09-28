"""BalanzaPeriodo y BalanzaPeriodoLinea (SPEC-028 T006): snapshot inmutable.

Research D3: el cierre intermedio NO crea asientos en el diario; persiste un
snapshot inmutable del balance de comprobacion del periodo. `total_debe ==
total_haber` se valida en el servicio antes de persistir y tambien con un CHECK
en la base de datos (partida doble estricta, constitucion I). Los triggers
`trg_balanza_periodo_*` / `trg_balanza_periodo_linea_*` (019_cierres.sql y su
espejo SQLite en `db/triggers.py`) rechazan UPDATE y DELETE (constitucion II).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class BalanzaPeriodo(Base):
    __tablename__ = "balanza_periodo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_balanza_periodo_empresa_id"),
        # Una balanza por cierre (periodo cerrado).
        UniqueConstraint("empresa_id", "periodo_id", name="uq_balanza_periodo_periodo"),
        # Constitucion I: el snapshot solo se persiste si cuadra exactamente.
        CheckConstraint("total_debe = total_haber", name="chk_balanza_periodo_cuadre"),
        CheckConstraint("n_lineas >= 0", name="chk_balanza_periodo_lineas"),
        CheckConstraint("fecha_fin >= fecha_ini", name="chk_balanza_periodo_rango"),
        ForeignKeyConstraint(
            ["empresa_id", "periodo_id"],
            ["periodo_cerrado.empresa_id", "periodo_cerrado.id"],
            name="fk_balanza_periodo_periodo",
        ),
        Index("ix_balanza_periodo_empresa_ejercicio", "empresa_id", "ejercicio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    periodo_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_ini: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_generacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    generado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    n_lineas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_debe: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    total_haber: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    #: Resultado provisional del periodo (grupos 6/7), research D4.
    resultado_provisional: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BalanzaPeriodoLinea(Base):
    __tablename__ = "balanza_periodo_linea"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_balanza_periodo_linea_empresa_id"),
        # Una linea por cuenta en cada snapshot.
        UniqueConstraint(
            "empresa_id", "balanza_id", "cuenta_id", name="uq_balanza_periodo_linea_cuenta"
        ),
        CheckConstraint("debe >= 0", name="chk_balanza_linea_debe"),
        CheckConstraint("haber >= 0", name="chk_balanza_linea_haber"),
        CheckConstraint("nivel >= 1 AND nivel <= 5", name="chk_balanza_linea_nivel"),
        ForeignKeyConstraint(
            ["empresa_id", "balanza_id"],
            ["balanza_periodo.empresa_id", "balanza_periodo.id"],
            name="fk_balanza_periodo_linea_cabecera",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "cuenta_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_balanza_periodo_linea_cuenta",
        ),
        Index("ix_balanza_periodo_linea_empresa_balanza", "empresa_id", "balanza_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    balanza_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    #: `AccountPlan.id` es BIGINT; la columna del data-model es coherente.
    cuenta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codigo: Mapped[str] = mapped_column(String(8), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    nivel: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    debe: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    haber: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    saldo: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal(0), server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
