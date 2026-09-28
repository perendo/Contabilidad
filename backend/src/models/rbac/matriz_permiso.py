"""Permission grant for one role on one operation within a company.

Deny-by-default: absence of a row means denied. The matrix only grants and is
evaluated per request (`empresa_id, rol_id` scoping; never cross-company).
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class MatrizPermiso(Base):
    __tablename__ = "matriz_permiso"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_matriz_permiso_tenant_id"),
        UniqueConstraint(
            "empresa_id", "rol_id", "permiso_id", name="uq_matriz_permiso_rol_permiso"
        ),
        Index(
            "ix_matriz_permiso_evaluacion",
            "empresa_id",
            "rol_id",
            "permiso_id",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "rol_id"],
            ["roles.empresa_id", "roles.id"],
            name="fk_matriz_permiso_rol",
        ),
        ForeignKeyConstraint(
            ["permiso_id"],
            ["permiso_operacion.id"],
            name="fk_matriz_permiso_operacion",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    rol_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    permiso_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    concesion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)