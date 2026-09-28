"""Rol row per company, mirroring the base roles of SPEC-003.

SPEC-003 stores the user's role as an enum on `UserCompany`; the permission
matrix needs a referenceable per-company entity, so `Rol` holds one row per
(empresa, nombre) for the base roles (ADMIN/ACCOUNTANT/READ_ONLY), seeded with
the company. `es_global_flag` is informational only: it never grants access.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class Rol(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_roles_tenant_id"),
        UniqueConstraint("empresa_id", "nombre", name="uq_roles_tenant_nombre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(40), nullable=False)
    es_global_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)