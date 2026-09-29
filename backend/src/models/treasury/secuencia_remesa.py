"""SecuenciaRemesa model: atomic correlative numbering per (empresa, ejercicio).

The row is locked with SELECT ... FOR UPDATE inside the same ACID transaction
that persists the remesa (constitución IV).
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class SecuenciaRemesa(Base):
    __tablename__ = "secuencia_remesa"
    __table_args__ = (
        # El nombre lo ponia la convencion como `uq_secuencia_remesa_empresa_id`, que
        # dice "clave de empresa" y en realidad es la clave de empresa **y ejercicio**:
        # hay una fila por ano. En un `\d` de PostgreSQL no se entiende, y la
        # convencion (`uq_%(table_name)s_%(column_0_name)s`) es la que hace que dos
        # unicos que empiezan por `empresa_id` choquen entre si.
        UniqueConstraint("empresa_id", "ejercicio", name="uq_secuencia_remesa_empresa_ejercicio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    ultimo_numero: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)