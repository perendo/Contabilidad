"""Correlative invoice numbering (SPEC-004 T009).

Atomic per (empresa_id, ejercicio) following the SPEC-002 pattern: rows are
locked with ``SELECT ... FOR UPDATE`` inside the caller's ACID transaction
and the next number is ``MAX(numero_seq) + 1``. The
``uq_invoice_empresa_ejercicio_numero`` constraint is the final arbiter for
a first concurrent insert.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.invoice import Invoice


async def next_numero_factura(db: AsyncSession, empresa_id: int, ejercicio: int) -> int:
    filas = (
        await db.execute(
            select(Invoice.numero_seq)
            .where(Invoice.empresa_id == empresa_id, Invoice.ejercicio == ejercicio)
            .with_for_update()
        )
    ).all()
    usados = [numero for (numero,) in filas]
    return (max(usados) if usados else 0) + 1


async def existe_numero_factura(db: AsyncSession, empresa_id: int, ejercicio: int, numero: int) -> bool:
    return (
        await db.scalar(
            select(Invoice.id).where(
                Invoice.empresa_id == empresa_id,
                Invoice.ejercicio == ejercicio,
                Invoice.numero_seq == numero,
            )
        )
    ) is not None
