"""Exportacion (SPEC-029 T006): registro de una exportacion integral del tenant.

Es un **snapshot inmutable** del estado del tenant (research D9): una vez en
estado `lista` no admite UPDATE ni DELETE, ni por servicio ni por trigger
(`chk_exportacion_immutable`, constitution II). Solo se admite la transicion
`en_proceso -> lista | fallida` que resuelve la propia generacion.

Correlatividad (constitution IV, research D10): `numero_exportacion` es unico y
correlativo por `(empresa_id, anio_creacion)`; lo asigna `persistir.py` con
`SELECT ... FOR UPDATE` sobre la ultima fila del par, con el UNIQUE como red de
seguridad final.

Multi-tenancy (constitution III): `empresa_id` en la clave unica, en los indices
y en las FKs compuestas; **nunca** se recibe del request.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base

#: Techo del MVP (research D5). Por encima se rechaza la generacion en vez de
#: agotar la memoria del backend; la via prevista para tenants enormes es
#: filtrar por rango de ejercicios (FR-005).
LIMITE_BYTES: int = 100 * 1024 * 1024


class TipoExportacion(str, Enum):
    INTEGRAL = "INTEGRAL"
    SII = "SII"


class EstadoExportacion(str, Enum):
    en_proceso = "en_proceso"
    lista = "lista"
    fallida = "fallida"


#: Estados terminales: bloquean cualquier UPDATE/DELETE posterior.
ESTADOS_FINALES: frozenset[EstadoExportacion] = frozenset(
    {EstadoExportacion.lista, EstadoExportacion.fallida}
)


class Exportacion(Base):
    __tablename__ = "exportacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_exportacion_empresa_id"),
        # Constitution IV: correlatividad sin saltos por (empresa, anio).
        UniqueConstraint(
            "empresa_id",
            "anio_creacion",
            "numero_exportacion",
            name="uq_exportacion_numero",
        ),
        CheckConstraint(
            "ejercicio_desde IS NULL OR ejercicio_hasta IS NULL"
            " OR ejercicio_desde <= ejercicio_hasta",
            name="chk_exportacion_rango",
        ),
        CheckConstraint("numero_exportacion > 0", name="chk_exportacion_numero_positivo"),
        CheckConstraint("n_bloques >= 0", name="chk_exportacion_bloques"),
        CheckConstraint("tamano_bytes IS NULL OR tamano_bytes >= 0", name="chk_exportacion_tamano"),
        Index("ix_exportacion_empresa_estado", "empresa_id", "estado"),
        Index("ix_exportacion_empresa_anio", "empresa_id", "anio_creacion"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    anio_creacion: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_exportacion: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[TipoExportacion] = mapped_column(
        SqlEnum(TipoExportacion, name="tipo_exportacion"), nullable=False
    )
    ejercicio_desde: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ejercicio_hasta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[EstadoExportacion] = mapped_column(
        SqlEnum(EstadoExportacion, name="estado_exportacion"),
        nullable=False,
        default=EstadoExportacion.en_proceso,
    )
    #: `users.id` es BIGINT en SPEC-003, no UUID: se guarda la identidad del
    #: actor como texto (mismo criterio que `journal_entry.created_by`).
    creado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completado_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    blob_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tamano_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    n_bloques: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mensaje_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def nombre_fichero(self) -> str:
        """Nombre de descarga del ZIP, segun `contracts/api-contracts.md`."""
        creado = self.created_at.strftime("%Y%m%d") if self.created_at else "00000000"
        return f"export_{self.empresa_id}_{self.numero_exportacion}_{creado}.zip"

    @property
    def descargable(self) -> bool:
        """`True` solo en estado `lista`: unica situacion con descarga (409 si no)."""
        return self.estado == EstadoExportacion.lista

    @property
    def por_megabytes(self) -> Decimal:
        """Tamano expresado en MiB con 4 decimales (solo para respuestas)."""
        if self.tamano_bytes is None:
            return Decimal(0)
        return (Decimal(self.tamano_bytes) / Decimal(1024 * 1024)).quantize(Decimal("0.0001"))
