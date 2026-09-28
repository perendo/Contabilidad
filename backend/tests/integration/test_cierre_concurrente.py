"""Concurrency test SPEC-004 T050: doble cierre simultáneo → un 200 y un 409.

Opt-in PostgreSQL real (``TEST_DATABASE_URL``): ``SELECT ... FOR UPDATE``
sobre ``fiscal_year`` no tiene equivalente en SQLite, igual que T040.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from models.acct.fiscal_year import FiscalYear
from services.closing.close_year import CierreError, cerrar_ejercicio

URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not URL, reason="TEST_DATABASE_URL no configurada (concurrencia solo en PostgreSQL)"
)

EMPRESA = 940401


@pytest.fixture
async def engine_concurrente() -> AsyncEngine:
    assert URL is not None
    engine = create_async_engine(URL)
    yield engine
    await engine.dispose()


async def _preparar(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social)"
                " VALUES (:e, 'K94040101', 'Cierre Conc SL')"
                " ON CONFLICT (company_id) DO NOTHING"
            ),
            {"e": EMPRESA},
        )
        await s.execute(
            text("DELETE FROM fiscal_year WHERE empresa_id = :e AND year = 2026"),
            {"e": EMPRESA},
        )
        s.add(
            FiscalYear(
                empresa_id=EMPRESA, year=2026,
                date_start=date(2026, 1, 1), date_end=date(2026, 12, 31),
            )
        )
        await s.commit()


async def _intento(engine: AsyncEngine) -> str:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        try:
            await cerrar_ejercicio(s, empresa_id=EMPRESA, year=2026, actor="t050")
            await s.commit()
            return "200"
        except CierreError:
            await s.rollback()
            return "409"


async def test_doble_cierre_concurrente_un_ganador(engine_concurrente) -> None:
    engine = engine_concurrente
    await _preparar(engine)
    resultados = await asyncio.gather(_intento(engine), _intento(engine))
    assert sorted(resultados) == ["200", "409"]
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        fy = await s.scalar(
            select(FiscalYear).where(
                FiscalYear.empresa_id == EMPRESA, FiscalYear.year == 2026
            )
        )
        assert fy is not None and fy.is_closed
