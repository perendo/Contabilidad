"""ConfiguracionInforme (SPEC-010 T005): agrupacion del plan por masa/partida.

Multi-tenant estricto (constitucion III): ``empresa_id`` en PK/indices/filtros.
Cada fila mapea un rango de cuentas ``[cuenta_ini, cuenta_fin]`` a una
agrupacion (masa/partida) del informe. Si no hay configuracion, las cuentas se
clasifican en "Otros" con aviso (research D1).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class InformeTipo(str, enum.Enum):
    BALANCE = "BALANCE"
    PYG = "PYG"
    EFE = "EFE"


class ActividadEfe(str, enum.Enum):
    operativa = "operativa"
    inversion = "inversion"
    financiacion = "financiacion"


class ConfiguracionInforme(Base):
    __tablename__ = "configuracion_informe"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_config_informe_tenant_id"),
        UniqueConstraint(
            "empresa_id",
            "ejercicio",
            "informe_tipo",
            "agrupacion_codigo",
            "cuenta_ini",
            name="uq_config_informe_regla",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    informe_tipo: Mapped[InformeTipo] = mapped_column(
        SqlEnum(InformeTipo, name="informe_tipo"), nullable=False
    )
    agrupacion_codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    agrupacion_nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    cuenta_ini: Mapped[str] = mapped_column(String(20), nullable=False)
    cuenta_fin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actividad_efe: Mapped[ActividadEfe | None] = mapped_column(
        SqlEnum(ActividadEfe, name="actividad_efe"), nullable=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )