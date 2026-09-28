"""SecuenciaReapertura (SPEC-028 T008): numeracion correlativa de solicitudes.

Constitucion IV: `numero_solicitud` es unico y correlativo por
`(empresa_id, ejercicio)`, asignado atomicamente con `SELECT ... FOR UPDATE`
dentro de la misma transaccion ACID que inserta la solicitud. El patron replica
`SecuenciaAsiento` de SPEC-002: la fila se asegura con
`INSERT ... ON CONFLICT DO NOTHING` antes del bloqueo para que dos
transacciones concurrentes que solicitan la primera vez no vean ambas `None`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class SecuenciaReapertura(Base):
    __tablename__ = "secuencia_reapertura"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "ejercicio", name="uq_secuencia_reapertura_pair"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ultimo_numero: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
