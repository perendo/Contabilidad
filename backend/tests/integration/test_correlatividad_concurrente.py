"""Concurrency test SPEC-002 T040: correlatividad bajo concurrencia (SC-006).

Verifica sobre PostgreSQL real (opt-in via ``TEST_DATABASE_URL``) que 20
asientos del mismo ``(empresa, ejercicio)`` asentados simultáneamente reciben
la serie correlativa 1..20 sin duplicados ni omisiones. ``SELECT ... FOR
UPDATE`` sobre ``journal_sequence`` no tiene equivalent en SQLite, por eso la
prueba es opt-in como ``test_pg_schema``.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from services.journal.entry_service import asentar, crear_borrador

URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not URL, reason="TEST_DATABASE_URL no configurada (concurrencia solo en PostgreSQL)"
)

EMPRESA = 930301


async def _seed_pgc_y_borradores(engine: AsyncEngine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social)"
                " VALUES (:e, 'K93030101', 'Concurrente SL')"
                " ON CONFLICT (company_id) DO NOTHING"
            ),
            {"e": EMPRESA},
        )
        await s.commit()
        filas = (
            await s.execute(
                text(
                    "SELECT id, code FROM account_plan"
                    " WHERE tenant_id = :e AND is_selectable AND is_active"
                    " ORDER BY level DESC, code"
                ),
                {"e": EMPRESA},
            )
        ).all()
    assert len(filas) >= 2, "el seed del PGC no dejó subcuentas apuntables"
    ids = [row[0] for row in filas[:2]]

    creados = []
    async with factory() as s:
        for i in range(20):
            entrada = await crear_borrador(
                s,
                empresa_id=EMPRESA,
                fecha=date(2026, 10, 1),
                concepto=f"Concurrente {i+1}",
                lineas=[
                    {"account_id": ids[0], "debit": "10.0000", "credit": "0"},
                    {"account_id": ids[1], "debit": "0", "credit": "10.0000"},
                ],
                actor="t040",
            )
            creados.append(entrada.id)
        await s.commit()
    return creados


async def test_20_asientos_concurrentes_serie_unica(engine_concurrente):
    engine = engine_concurrente
    creados = await _seed_pgc_y_borradores(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _post(entry_id):
        async with factory() as s:
            await asentar(
                s,
                empresa_id=EMPRESA,
                entry_id=entry_id,
                actor="t040",
            )
            await s.commit()

    resultados = await asyncio.gather(*(_post(eid) for eid in creados), return_exceptions=True)
    errores = [r for r in resultados if isinstance(r, Exception)]
    assert errores == [], f"hubo errores de concurrencia: {errores!r}"

    async with factory() as s:
        numeros = (
            await s.scalars(
                text(
                    "SELECT numero_asiento FROM journal_entry"
                    " WHERE empresa_id = :e ORDER BY numero_asiento"
                ),
                {"e": EMPRESA},
            )
        ).all()
    assert list(numeros) == list(range(1, 21))


@pytest.fixture
async def engine_concurrente() -> AsyncEngine:
    assert URL is not None
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        existe = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables"
                    " WHERE table_schema='public' AND table_name='journal_entry'"
                )
            )
        ).scalar()
    if not existe:
        await engine.dispose()
        pytest.skip("journal_entry ausente: ejecuta db.migrate sobre TEST_DATABASE_URL")
    yield engine
    await engine.dispose()