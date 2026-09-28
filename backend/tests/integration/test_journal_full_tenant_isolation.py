"""Integration tests SPEC-002 T038: aislamiento multi-tenant completo (SC-002)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo


async def test_ninguna_operacion_cruzada(journal_api):
    """GET/asentar/anular desde B sobre asiento de A → 404 en los tres casos."""
    creado = journal_api.crear(fecha="2026-10-01", concepto="De A")
    entry_a = creado.json()["id"]

    assert journal_api.detalle(entry_a, empresa_id=20).status_code == 404
    assert journal_api.asentar(entry_a, empresa_id=20).status_code == 404
    assert journal_api.anular(entry_a, empresa_id=20).status_code == 404
    # B no ve lista de A
    diario = journal_api.diario(
        empresa_id=20, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert diario.json()["total"] == 0


async def test_reversal_de_b_nunca_enlaza_original_de_a(journal_api):
    creado_a = journal_api.crear(empresa_id=10, fecha="2026-10-01", concepto="A")
    entry_a_str = creado_a.json()["id"]
    entry_a = uuid.UUID(entry_a_str)
    assert journal_api.asentar(entry_a_str, empresa_id=10).status_code == 200

    creado_b = journal_api.crear(empresa_id=20, fecha="2026-10-01", concepto="B")
    entry_b = creado_b.json()["id"]
    assert journal_api.asentar(entry_b, empresa_id=20).status_code == 200
    anulacion_b = journal_api.anular(entry_b, empresa_id=20)
    assert anulacion_b.status_code == 201

    async def _reversales(s):
        filas = list(
            await s.scalars(
                select(JournalEntry).where(
                    JournalEntry.tipo == JournalEntryTipo.REVERSAL,
                    JournalEntry.empresa_id == 20,
                )
            )
        )
        return [(r.original_id == entry_a) for r in filas]

    # Ningún reversal de B apunta al original de A
    assert await journal_api.consultar(_reversales) == [False]


async def test_lineas_y_cuentas_estrictamente_de_su_empresa(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="A cuenta")
    entry_a = uuid.UUID(creado.json()["id"])
    assert journal_api.asentar(creado.json()["id"], empresa_id=10).status_code == 200

    async def _cuentas_empresa(s):
        return set(
            await s.scalars(
                select(JournalEntryLine.cuenta).where(
                    JournalEntryLine.journal_entry_id == entry_a,
                    JournalEntryLine.empresa_id == 20,
                )
            )
        )

    assert await journal_api.consultar(_cuentas_empresa) == set()


async def test_conteo_global_correcto_por_empresa(journal_api):
    for empresa in (10, 20):
        creado = journal_api.crear(empresa_id=empresa, fecha="2026-10-01", concepto="Cnt")
        assert journal_api.asentar(creado.json()["id"], empresa_id=empresa).status_code == 200

    async def _count(s):
        return await s.scalar(
            select(func.count()).select_from(JournalEntry).where(
                JournalEntry.empresa_id.in_([10, 20])
            )
        )

    assert await journal_api.consultar(_count) == 2