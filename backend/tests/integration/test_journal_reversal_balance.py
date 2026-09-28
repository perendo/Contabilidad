"""Integration tests SPEC-002 T029: REVERSAL balanceado (US3)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)


async def test_reversal_importes_invertidos_y_balance(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Venta original")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200

    anulacion = journal_api.anular(entry_id, fecha="2026-10-05", concepto="Baja")
    assert anulacion.status_code == 201
    body = anulacion.json()
    assert body["estado_original"] == "CANCELLED"
    assert body["numero_reversal"] == 2
    assert body["balance"]["suma_debe"] == body["balance"]["suma_haber"] == "100.0000"

    reversal_id = uuid.UUID(body["id_reversal"])
    original_id = uuid.UUID(entry_id)

    async def _datos(s):
        reversal = await s.scalar(select(JournalEntry).where(JournalEntry.id == reversal_id))
        original = await s.scalar(select(JournalEntry).where(JournalEntry.id == original_id))
        lineas_rev = list(
            await s.scalars(
                select(JournalEntryLine)
                .where(JournalEntryLine.journal_entry_id == reversal_id)
                .order_by(JournalEntryLine.line_no)
            )
        )
        lineas_orig = list(
            await s.scalars(
                select(JournalEntryLine)
                .where(JournalEntryLine.journal_entry_id == original_id)
                .order_by(JournalEntryLine.line_no)
            )
        )
        return reversal, original, lineas_rev, lineas_orig

    reversal, original, lineas_rev, lineas_orig = await journal_api.consultar(_datos)
    assert reversal.tipo == JournalEntryTipo.REVERSAL
    assert reversal.estado == JournalEntryEstado.POSTED
    assert reversal.original_id == original_id
    assert reversal.concepto == "Baja"
    assert reversal.fecha.isoformat() == "2026-10-05"
    assert reversal.numero_asiento == 2

    assert len(lineas_rev) == len(lineas_orig) == 2
    # Debe/Haber invertidos respecto al original
    assert lineas_rev[0].debe == Decimal("0.0000")
    assert lineas_rev[0].haber == Decimal("100.0000")
    assert lineas_rev[0].cuenta == "4300"
    assert lineas_rev[1].debe == Decimal("100.0000")
    assert lineas_rev[1].haber == Decimal("0.0000")
    assert lineas_rev[1].cuenta == "5720"

    # El original no se modifica (payload intacto), solo estado → CANCELLED
    assert original.tipo == JournalEntryTipo.GENERAL
    assert original.concepto == "Venta original"
    assert original.numero_asiento == 1
    assert original.estado == JournalEntryEstado.CANCELLED
    assert {l.cuenta for l in lineas_orig} == {"4300", "5720"}
    assert [l.debe for l in lineas_orig] == [Decimal("100.0000"), Decimal("0.0000")]
    assert [l.haber for l in lineas_orig] == [Decimal("0.0000"), Decimal("100.0000")]


async def test_reversal_misma_cantidad_lineas(journal_api):
    c = journal_api.cuentas["a"]
    lineas = [
        {"account_id": c["4300"], "debit": "150.0000", "credit": "0", "detail": "cliente"},
        {"account_id": c["5720"], "debit": "0", "credit": "100.0000", "detail": "banco"},
        {"account_id": c["5720"], "debit": "0", "credit": "50.0000", "detail": "banco2"},
    ]
    creado = journal_api.crear(fecha="2026-10-01", concepto="Multilinea", lineas=lineas)
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200
    anulacion = journal_api.anular(entry_id)
    assert anulacion.status_code == 201
    assert anulacion.json()["balance"]["suma_debe"] == "150.0000"
    assert anulacion.json()["balance"]["suma_haber"] == "150.0000"

    reversal_id = uuid.UUID(anulacion.json()["id_reversal"])

    async def _n_lineas(s):
        return await s.scalar(
            select(func.count()).select_from(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == reversal_id
            )
        )

    assert await journal_api.consultar(_n_lineas) == 3