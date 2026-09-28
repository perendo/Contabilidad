"""Correlative asiento numbering (SPEC-002 T008). Atomic SELECT ... FOR UPDATE
inside the same ACID transaction as the POSTED write.

`next_numero` garantiza una fila de secuencia (INSERT ON CONFLICT DO NOTHING)
antes del ``SELECT ... FOR UPDATE``: sin ella, dos transacciones concurrentes
que asientan por primera vez un ``(empresa_id, ejercicio)`` verían ambos
``None``, romperían la correlatividad o violarían ``uq_journal_sequence_pair``.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal_sequence import SecuenciaAsiento


async def next_numero(db: AsyncSession, empresa_id: int, ejercicio: int) -> int:
    # Asegura la fila de secuencia: INSERT ... ON CONFLICT DO NOTHING es
    # idempotente y no interfiere con el for_update posterior (PG y SQLite).
    await db.execute(
        text(
            "INSERT INTO journal_sequence (empresa_id, ejercicio, ultimo_numero)"
            " VALUES (:empresa_id, :ejercicio, 0)"
            " ON CONFLICT DO NOTHING"
        ),
        {"empresa_id": empresa_id, "ejercicio": ejercicio},
    )
    seq = await db.scalar(
        select(SecuenciaAsiento)
        .where(
            SecuenciaAsiento.empresa_id == empresa_id,
            SecuenciaAsiento.ejercicio == ejercicio,
        )
        .with_for_update()
    )
    assert seq is not None
    seq.ultimo_numero += 1
    await db.flush()
    return seq.ultimo_numero