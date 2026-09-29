"""CobroConciliado model: idempotency key for SPEC-013 bank reconciliation.

A (empresa_id, movimiento_id) pair confirms the collection of exactly one
recibo; retrying the same movimiento returns the stored asiento (FR-007).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class CobroConciliado(Base):
    __tablename__ = "cobro_conciliado"
    __table_args__ = (
        # Nombre explicito, por la colision con el `("empresa_id", "id")` de abajo: la
        # convencion de nombres usa solo la primera columna y las dos empiezan por
        # `empresa_id`. Es la deduplicacion del cruce entre conciliacion y remesa: un
        # movimiento bancario no se cobra dos veces. Ver `devolucion.py` y el guard
        # `test_no_hay_dos_restricciones_con_el_mismo_nombre`.
        UniqueConstraint(
            "empresa_id", "movimiento_id",
            name="uq_cobro_conciliado_empresa_movimiento",
        ),
        UniqueConstraint("empresa_id", "id"),
        ForeignKeyConstraint(
            ["empresa_id", "recibo_remesa_id"],
            ["recibo_remesa.empresa_id", "recibo_remesa.id"],
            name="fk_cobro_conciliado_empresa_recibo",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "journal_entry_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_cobro_conciliado_empresa_asiento",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    movimiento_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    recibo_remesa_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )