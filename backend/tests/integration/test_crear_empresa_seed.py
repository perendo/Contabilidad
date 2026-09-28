"""Tests SPEC-003 US4 (T027): crear empresa → ADMIN + seed PGC base."""

from __future__ import annotations

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.companies import router as companies_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.acct.account_plan import AccountPlan
from models.iam.user import User
from models.iam.user_company import UserRol
from services.auth.company_service import crear_empresa
from services.auth.security import emit_token, hash_password
from services.auth.session import listar_empresas_usuario


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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await session.commit()
        return emit_token(1)

    token = anyio.run(_setup)

    app = FastAPI()
    app.include_router(companies_router)

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
        yield client, token, factory
    anyio.run(_dispose, engine)


async def _dispose(engine) -> None:
    await engine.dispose()


async def test_crear_empresa_da_admin_y_seed(api_client) -> None:
    _, _, factory = api_client
    async with factory() as session:
        company, rel = await crear_empresa(
            session, user_id=1, nif="B12345678", razon_social="Nueva SL"
        )
        assert rel.role == UserRol.ADMIN
        assert rel.is_default is True
        empresas = await listar_empresas_usuario(session, 1)
        assert company.company_id in [e["company_id"] for e in empresas]
        grupos = await session.scalar(
            select(func.count(AccountPlan.id)).where(
                AccountPlan.tenant_id == company.company_id,
                AccountPlan.level == 1,
            )
        )
        assert grupos is not None and grupos >= 7
        await session.rollback()


async def test_post_companies_201_con_admin_y_defecto(api_client) -> None:
    client, token, _ = api_client
    resp = client.post(
        "/api/v1/companies",
        json={"nif": "B87654321", "razon_social": "Otra SL"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["nif"] == "B87654321"
    assert body["role"] == "ADMIN"
    assert body["default_company_id"] == body["company_id"]


async def test_post_companies_sin_auth_401(api_client) -> None:
    client, _, _ = api_client
    resp = client.post(
        "/api/v1/companies", json={"nif": "B00000000", "razon_social": "X"}
    )
    assert resp.status_code == 401
