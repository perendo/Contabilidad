"""Numeracion correlativa de solicitudes de reapertura (SPEC-028 T044).

Constitucion IV: `next_numero_solicitud` asigna el siguiente numero por
`(empresa_id, ejercicio)` bajo `SELECT ... FOR UPDATE`, dentro de la misma
transaccion ACID que inserta la `SolicitudReapertura`. El patron replica
`services.journal.sequence.next_numero` (SPEC-002): sin asegurar la fila de
secuencia, dos transacciones concurrentes que solicitan por primera vez verian
ambas `None` y romperian la correlatividad.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.closing.secuencia_reapertura import SecuenciaReapertura


async def next_numero_solicitud(db: AsyncSession, empresa_id: int, ejercicio: int) -> int:
    """Siguiente `numero_solicitud` atomico para (empresa, ejercicio)."""
    await db.execute(
        text(
            "INSERT INTO secuencia_reapertura (empresa_id, ejercicio, ultimo_numero)"
            " VALUES (:empresa_id, :ejercicio, 0)"
            " ON CONFLICT DO NOTHING"
        ),
        {"empresa_id": empresa_id, "ejercicio": ejercicio},
    )
    seq = await db.scalar(
        select(SecuenciaReapertura)
        .where(
            SecuenciaReapertura.empresa_id == empresa_id,
            SecuenciaReapertura.ejercicio == ejercicio,
        )
        .with_for_update()
    )
    assert seq is not None
    seq.ultimo_numero += 1
    await db.flush()
    return seq.ultimo_numero
