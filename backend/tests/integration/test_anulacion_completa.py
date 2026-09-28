"""T114: Test integración anulación completa (SPEC-006 US3).

Crear 3:2 por HTTP, anular, verificar rectificativo con líneas invertidas,
original intacto y ambos balanceados.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Compra"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Alquiler"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldo"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Prov A"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Prov B"},
]

BODY = {"fecha": "2026-01-15", "concepto": "Gastos varios", "lineas": LINEAS_3_2}


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_anulacion_completa_via_http(asientos_client):
    client, token, factory = asientos_client
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text
    original_id = creado.json()["id"]

    anulacion = client.post(
        f"/api/v1/asientos/{original_id}/anular", headers=_hh(token, 10)
    )
    assert anulacion.status_code == 201, anulacion.text
    rect = anulacion.json()["asiento_rectificativo"]
    assert rect["tipo"] == "REVERSAL"
    assert anulacion.json()["asiento_original_id"] == original_id
    assert rect["n_lineas"] == 5
    assert rect["total_debe"] == rect["total_haber"] == "500.0000"

    async def _comparar() -> dict:
        async with factory() as session:
            n_entries = await session.scalar(select(func.count()).select_from(JournalEntry))
            n_lines_original = await session.scalar(
                select(func.count()).select_from(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == uuid.UUID(original_id)
                )
            )
            rect_lin = list(
                    (
                        await session.scalars(
                            select(JournalEntryLine).where(
                                JournalEntryLine.journal_entry_id == uuid.UUID(rect["id"])
                            )
                        )
                    ).all()
                )
            rev_debe = sum((l.debe for l in rect_lin), Decimal(0))
            rev_haber = sum((l.haber for l in rect_lin), Decimal(0))
            return {
                "n_entries": int(n_entries),
                "n_lines_original": int(n_lines_original),
                "rev_debe": rev_debe,
                "rev_haber": rev_haber,
            }

    loop = asyncio.new_event_loop()
    try:
        ver = loop.run_until_complete(_comparar())
    finally:
        loop.close()
    assert ver["n_entries"] == 2
    assert ver["n_lines_original"] == 5
    assert ver["rev_debe"] == ver["rev_haber"] == Decimal("500.0000")

    original = client.get(f"/api/v1/asientos/{original_id}", headers=_hh(token, 10))
    assert original.json()["estado"] == "CANCELLED"
    assert original.json()["tipo"] == "GENERAL"
    assert original.json()["asiento_original_id"] is None