"""Tests SPEC-003 US3 (T023): operar con empresa no autorizada → 403 sin fugas."""

from __future__ import annotations

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.acct.accounts import router as accounts_router
from api.journal.journal import router as journal_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.acct.account_plan import AccountPlan
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password
from tests.conftest import crear_empresas


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
            await crear_empresas(
                session, 10, 30,
                nifs={10: "A00000001", 30: "C00000003"},
                razones_sociales={10: "Diez SL", 30: "Treinta SL"},
            )
            session.add(
                UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True)
            )
            await session.flush()
            cuentas: dict[str, int] = {}
            for codigo, nombre in (
                ("4", "Clientes"), ("43", "Clientes varios"), ("430", "Clientes emisores"),
                ("4300", "Clientes detalle"),
            ):
                nivel = len(codigo)
                padre = cuentas.get(codigo[:-1]) if len(codigo) > 1 else None
                cuenta = AccountPlan(
                    tenant_id=10, code=codigo, name=nombre,
                    parent_id=padre, level=nivel, is_active=True,
                )
                session.add(cuenta)
                await session.flush()
                cuentas[codigo] = cuenta.id
            await session.commit()
        return emit_token(1)

    token = anyio.run(_setup)

    app = FastAPI()
    app.include_router(accounts_router)
    app.include_router(journal_router)

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


def _hh(token: str, empresa_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa_id)}


def test_cuentas_cross_empresa_403_sin_fugas(api_client) -> None:
    client, token = api_client
    for method, ruta, kwargs in [
        ("GET", "/api/v1/accounts/tree", {}),
        ("GET", "/api/v1/accounts/suggest", {"params": {"q": "43"}}),
        ("GET", "/api/v1/accounts/1", {}),
        ("POST", "/api/v1/accounts", {"json": {"code": "4400", "name": "X"}}),
    ]:
        resp = getattr(client, method.lower())(ruta, headers=_hh(token, 30), **kwargs)
        assert resp.status_code == 403, (method, ruta, resp.status_code)
        assert "Diez" not in resp.text and "4300" not in resp.text


def test_asientos_cross_empresa_403_sin_fugas(api_client) -> None:
    client, token = api_client
    resp = client.get(
        "/api/v1/journal/entries",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        headers=_hh(token, 30),
    )
    assert resp.status_code == 403
    assert "Diez" not in resp.text
    resp = client.post(
        "/api/v1/journal/entries",
        json={"fecha": "2026-01-15", "concepto": "X", "lineas": []},
        headers=_hh(token, 30),
    )
    assert resp.status_code == 403
