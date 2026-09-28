"""Integration tests SPEC-002 T037: constitución del motor (I, II, III, V)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine


async def test_partida_doble_global_por_empresa(journal_api):
    """Tras crear/asentar/anular, SUM(Debe) == SUM(Haber) por empresa."""
    entradas = []
    for _ in range(3):
        creado = journal_api.crear(fecha="2026-10-01", concepto="Iteración")
        entradas.append(creado.json()["id"])
    for entry_id in entradas:
        assert journal_api.asentar(entry_id).status_code == 200
    assert journal_api.anular(entradas[1]).status_code == 201

    async def _totales(s):
        debe = await s.scalar(
            select(func.sum(JournalEntryLine.debe)).where(
                JournalEntryLine.empresa_id == 10
            )
        )
        haber = await s.scalar(
            select(func.sum(JournalEntryLine.haber)).where(
                JournalEntryLine.empresa_id == 10
            )
        )
        return Decimal(str(debe)), Decimal(str(haber))

    debe, haber = await journal_api.consultar(_totales)
    assert debe == haber
    assert debe > 0


async def test_importes_decimal_no_float(journal_api):
    import uuid

    creado = journal_api.crear(fecha="2026-10-01", concepto="Decimal estricto")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200
    entry_uuid = uuid.UUID(entry_id)

    async def _tipos(s):
        filas = list(
            await s.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == entry_uuid
                )
            )
        )
        return [(type(l.debe).__name__, type(l.haber).__name__) for l in filas]

    tipos = await journal_api.consultar(_tipos)
    assert tipos == [("Decimal", "Decimal"), ("Decimal", "Decimal")]


async def test_secuencia_vacia_tras_bucle_sin_rastro(journal_api):
    """Crear+asentar secuencial no deja agujeros y el balance se mantiene."""
    for _ in range(4):
        creado = journal_api.crear(fecha="2026-10-01", concepto="Serie")
        assert journal_api.asentar(creado.json()["id"]).status_code == 200

    async def _numeros(s):
        return list(
            await s.scalars(
                select(JournalEntry.numero_asiento)
                .where(JournalEntry.empresa_id == 10)
                .order_by(JournalEntry.numero_asiento)
            )
        )

    assert await journal_api.consultar(_numeros) == [1, 2, 3, 4]


async def test_empresas_aisladas_en_totales(journal_api):
    """La actividad de A no infla los totales de B y viceversa."""
    creado = journal_api.crear(empresa_id=20, fecha="2026-10-01", concepto="Solo B")
    assert journal_api.asentar(creado.json()["id"], empresa_id=20).status_code == 200

    async def _debe_empresa(s, empresa):
        total = await s.scalar(
            select(func.sum(JournalEntryLine.debe)).where(
                JournalEntryLine.empresa_id == empresa
            )
        )
        return Decimal(str(total or 0))

    assert await journal_api.consultar(lambda s: _debe_empresa(s, 10)) == Decimal(0)
    assert await journal_api.consultar(lambda s: _debe_empresa(s, 20)) == Decimal("100.0000")