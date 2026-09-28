"""Integration: switch-company HTTP contract (SPEC-003 US2 / T018-T019)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.auth.auth import router as auth_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password
from tests.conftest import crear_empresas


@pytest.fixture
def auth_client():
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

    async def _setup() -> tuple[int, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            user = User(
                id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana"
            )
            session.add(user)
            await crear_empresas(
                session, 10, 20,
                nifs={10: "A00000001", 20: "B00000002"},
                razones_sociales={10: "Diez SL", 20: "Veinte SL"},
            )
            session.add_all(
                [
                    UserCompany(
                        id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True
                    ),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ACCOUNTANT),
                ]
            )
            await session.commit()
        return 1, emit_token(1)

    import anyio

    _user_id, token = anyio.run(_setup)

    app = FastAPI()
    app.include_router(auth_router)

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
        yield client, token
    anyio.run(_dispose, engine)


async def _dispose(engine) -> None:
    await engine.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_switch_200(auth_client) -> None:
    client, token = auth_client
    resp = client.post("/api/v1/auth/switch-company", json={"company_id": 20}, headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_id"] == 20
    assert body["role"] == "ACCOUNTANT"
    assert body["razon_social"] == "Veinte SL"


def test_switch_sin_relacion_403(auth_client) -> None:
    client, token = auth_client
    resp = client.post(
        "/api/v1/auth/switch-company", json={"company_id": 999}, headers=_auth(token)
    )
    assert resp.status_code == 403


def test_switch_body_invalido_422(auth_client) -> None:
    client, token = auth_client
    resp = client.post("/api/v1/auth/switch-company", json={"company_id": 0}, headers=_auth(token))
    assert resp.status_code == 422


def test_switch_sin_token_401(auth_client) -> None:
    client, _ = auth_client
    resp = client.post("/api/v1/auth/switch-company", json={"company_id": 20})
    assert resp.status_code == 401
