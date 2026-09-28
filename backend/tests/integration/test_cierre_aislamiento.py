"""Tests SPEC-004 US3 (T032): cerrar ejercicio ajeno → 404/403 sin efectos."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.reports.fiscal import router as fiscal_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.acct.fiscal_year import FiscalYear
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password


@pytest.fixture
def api_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup() -> tuple[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana"),
                    User(id=2, email="luis@x.es", password_hash=hash_password("pw"), full_name="Luis"),
                    Company(company_id=10, nif="A00000001", razon_social="Diez SL"),
                    Company(company_id=20, nif="B00000002", razon_social="Veinte SL"),
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=2, company_id=20, role=UserRol.ADMIN, is_default=True),
                    FiscalYear(
                        empresa_id=20, year=2026,
                        date_start=date(2026, 1, 1), date_end=date(2026, 12, 31),
                    ),
                ]
            )
            await session.commit()
        return emit_token(1), emit_token(2)

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        token_a, token_b = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(fiscal_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, token_a, token_b
    _cerrar(engine)


def _cerrar(engine) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def test_cerrar_ejercicio_ajeno_403(api_client) -> None:
    client, token_a, _ = api_client
    resp = client.post(
        "/api/v1/fiscal-years/2026/close",
        headers={"Authorization": f"Bearer {token_a}", "X-Empresa-Activa": "20"},
    )
    assert resp.status_code == 403


def test_cerrar_ejercicio_inexistente_propio_404(api_client) -> None:
    client, token_a, _ = api_client
    resp = client.post(
        "/api/v1/fiscal-years/2026/close",
        headers={"Authorization": f"Bearer {token_a}", "X-Empresa-Activa": "10"},
    )
    assert resp.status_code == 404
