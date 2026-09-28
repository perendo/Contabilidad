"""Anulación de asientos multilínea (SPEC-006 US3 T112).

Envuelve `services.journal.reversal.anular` (SPEC-002): genera el asiento
``REVERSAL`` con todas las líneas invertidas (Debe ⇄ Haber), enlazado al
original vía ``original_id``, sin modificar el original (constitución II) y
dentro de la misma transacción ACID con auditoría. Devuelve el payload del
contrato ``/api/v1/asientos/{id}/anular``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine
from services.journal.reversal import anular

CUATRO = "{:0.4f}"


async def anular_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    entry_id: uuid.UUID,
    actor: str | None = None,
    fecha: date | None = None,
    concepto: str | None = None,
) -> dict:
    """Anula un asiento multilínea y devuelve el rectificativo del contrato."""
    resultado = await anular(
        db,
        empresa_id=empresa_id,
        entry_id=entry_id,
        actor=actor,
        fecha=fecha,
        concepto=concepto,
    )
    reversal_id = uuid.UUID(resultado["id_reversal"])

    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == reversal_id,
            )
        )
    ).all()
    total_debe = sum((l.debe for l in lineas), Decimal(0))
    total_haber = sum((l.haber for l in lineas), Decimal(0))

    original = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id, JournalEntry.id == entry_id
        )
    )
    assert original is not None

    return {
        "asiento_rectificativo": {
            "id": resultado["id_reversal"],
            "numero_asiento": resultado["numero_reversal"],
            "tipo": "REVERSAL",
            "total_debe": CUATRO.format(total_debe),
            "total_haber": CUATRO.format(total_haber),
            "n_lineas": len(list(lineas)),
        },
        "asiento_original_id": str(original.id),
    }


__all__ = ["anular_asiento"]