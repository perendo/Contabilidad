"""Anulación de asientos (SPEC-002 US3): asiento REVERSAL balanceado.

Al anular un ``POSTED`` se genera, en la misma transacción ACID, un asiento
``REVERSAL`` con los importes invertidos (Debe ⇄ Haber) y ``original_id``
enlazado; el original pasa a ``CANCELLED`` sin otra modificación. Rechaza
doble anulación (409) y ejercicios cerrados (400). El reverse inserta el
rectificativo directamente como ``POSTED`` y marca el original ``CANCELLED``,
la única transición permitida por los triggers de inmutabilidad.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from services.audit.writer import audit_escribir
from services.journal.entry_service import (
    _validar_ejercicio,
    _validar_lineas,
    error,
)
from services.journal.sequence import next_numero


async def anular(
    db: AsyncSession,
    *,
    empresa_id: int,
    entry_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
    fecha: date | None = None,
    concepto: str | None = None,
) -> dict:
    original = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.id == entry_id,
        )
    )
    if original is None:
        raise error("asiento_no_encontrado", "Asiento inexistente en la empresa activa")
    if original.estado != JournalEntryEstado.POSTED:
        raise error(
            "estado_invalido",
            "El asiento no está POSTED (ya anulado o no asentado)",
        )

    fecha_fin = fecha or datetime.now(timezone.utc).date()
    await _validar_ejercicio(db, empresa_id, fecha_fin)
    ejercicio = fecha_fin.year

    lineas_raw = (
        await db.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == original.id,
                JournalEntryLine.empresa_id == empresa_id,
            )
        )
    ).all()
    if not lineas_raw:
        raise error("lineas_insuficientes", "El asiento original no tiene líneas")

    # Re-validar cuentas/balance del original (defensa en profundidad).
    await _validar_lineas(
        db,
        empresa_id,
        [
            {
                "account_id": l.account_id if l.account_id is not None else l.cuenta,
                "debit": l.debe,
                "credit": l.haber,
                "detail": l.descripcion,
            }
            for l in lineas_raw
        ],
    )

    concepto_fin = concepto or f"Anulación de asiento {original.numero_asiento}"
    numero = await next_numero(db, empresa_id, ejercicio)

    reversal = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha_fin,
        tipo=JournalEntryTipo.REVERSAL,
        concepto=concepto_fin,
        estado=JournalEntryEstado.POSTED,
        numero_asiento=numero,
        original_id=original.id,
        created_by=actor,
    )
    if reversal.id is None:
        reversal.id = uuid.uuid4()
    db.add(reversal)
    await db.flush()

    suma_debe = Decimal(0)
    suma_haber = Decimal(0)
    for i, linea in enumerate(lineas_raw, start=1):
        # importes invertidos: Debe ⇄ Haber
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=reversal.id,
                account_id=linea.account_id,
                line_no=i,
                cuenta=linea.cuenta,
                debe=linea.haber,
                haber=linea.debe,
                descripcion=linea.descripcion,
            )
        )
        suma_debe += linea.haber
        suma_haber += linea.debe
    await db.flush()

    original.estado = JournalEntryEstado.CANCELLED
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="REVERSAL",
        entity="journal_entry",
        entity_id=str(reversal.id),
        ip=ip,
        payload={
            "original_id": str(original.id),
            "numero": numero,
            "ejercicio": ejercicio,
        },
    )
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CANCELLED",
        entity="journal_entry",
        entity_id=str(original.id),
        ip=ip,
        payload={"numero_reversal": numero, "original_numero": original.numero_asiento},
    )
    await db.flush()

    return {
        "id_reversal": str(reversal.id),
        "numero_reversal": numero,
        "estado_original": original.estado.value,
        "balance": {
            "suma_debe": f"{suma_debe:0.4f}",
            "suma_haber": f"{suma_haber:0.4f}",
        },
    }