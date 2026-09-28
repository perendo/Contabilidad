"""JerarquiaCentro model (SPEC-017 D1: closure table).

Materializa todos los pares (ancestro_id, descendiente_id) de la jerarquía de
centros de una empresa, con `profundidad` (0 = el propio nodo). Permite agregar
subtotales por ancestro con un único JOIN (decisión D1 del research). Se
mantiene en la misma transacción ACID que la alta/reasignación del centro.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    SmallInteger,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class JerarquiaCentro(Base):
    __tablename__ = "jerarquia_centro"
    __table_args__ = (
        PrimaryKeyConstraint("empresa_id", "ancestro_id", "descendiente_id"),
        ForeignKeyConstraint(
            ["empresa_id", "ancestro_id"],
            ["centro_coste.empresa_id", "centro_coste.id"],
            name="fk_jerarquia_centro_ancestro",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "descendiente_id"],
            ["centro_coste.empresa_id", "centro_coste.id"],
            name="fk_jerarquia_centro_descendiente",
        ),
    )

    empresa_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ancestro_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    descendiente_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    profundidad: Mapped[int] = mapped_column(SmallInteger, nullable=False)