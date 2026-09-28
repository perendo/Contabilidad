"""Tests SPEC-004 Polish (T048): B ejecuta informes/cierre de A → 403/404."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.reports.fiscal import router as fiscal_router
from api.reports.informes import router as informes_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=2, email="luis@x.es", password_hash=hash_password("pw"), full_name="Luis"),
                    Company(company_id=10, nif="A00000001", razon_social="Diez SL"),
                    Company(company_id=20, nif="B00000002", razon_social="Veinte SL"),
                    UserCompany(id=2, user_id=2, company_id=20, role=UserRol.ADMIN, is_default=True),
                ]
            )
            await session.commit()
        return emit_token(2)

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        token_b = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(informes_router)
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
        yield client, token_b
    _cerrar(engine)


def _cerrar(engine) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def _hb(token_b: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_b}", "X-Empresa-Activa": "10"}


def test_b_informes_y_cierre_de_a_denegados_sin_fugas(api_client) -> None:
    client, token_b = api_client
    casos = [
        ("GET", "/api/v1/reports/trial-balance",
         {"params": {"date_from": "2026-01-01", "date_to": "2026-12-31"}}),
        ("GET", "/api/v1/reports/ledger/1", {}),
        ("GET", "/api/v1/fiscal-years", {}),
        ("POST", "/api/v1/fiscal-years/2026/close", {}),
    ]
    for method, ruta, kwargs in casos:
        resp = getattr(client, method.lower())(ruta, headers=_hb(token_b), **kwargs)
        assert resp.status_code in (403, 404), (method, ruta, resp.status_code)
        assert "Diez" not in resp.text and "A00000001" not in resp.text
