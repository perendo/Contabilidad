"""Router configuration tests: versioned prefix and session dependency (T002)."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.treasury.deps import get_empresa_id
from api.treasury.routes import router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password
from tests.conftest import crear_empresa


def test_router_uses_versioned_prefix():
    assert router.prefix == "/api/v1"


def test_router_declares_session_dependency():
    dependencies = [dependency.dependency for dependency in router.dependencies]
    assert get_empresa_id in dependencies


def _probe_client(token: str):
    probe = APIRouter(prefix=router.prefix, dependencies=router.dependencies)

    @probe.get("/_probe")
    def _probe(active_empresa_id: int = Depends(get_empresa_id)):
        return {"empresa_id": active_empresa_id}

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

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await crear_empresa(session, 9, nif="A00000009", razon_social="Nueve SL")
            await session.flush()
            session.add(
                UserCompany(id=1, user_id=1, company_id=9, role=UserRol.ADMIN, is_default=True)
            )
            await session.commit()

    anyio.run(_setup)

    app = FastAPI()
    app.include_router(probe)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), token


def _token() -> str:
    return emit_token(1)


def test_endpoint_requires_authenticated_session():
    client, _ = _probe_client(_token())
    assert client.get("/api/v1/_probe").status_code == 401


def test_endpoint_receives_session_empresa_id():
    client, token = _probe_client(_token())
    response = client.get(
        "/api/v1/_probe",
        headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": "9"},
    )
    assert response.status_code == 200
    assert response.json() == {"empresa_id": 9}
