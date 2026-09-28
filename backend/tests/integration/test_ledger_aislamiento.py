"""Tests SPEC-004 US2 (T021): mayor cross-empresa → 404 sin datos."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.reports.informes import router as informes_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.acct.account_plan import AccountPlan
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password
from tests.conftest import crear_empresa


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

    async def _setup() -> tuple[str, int]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await crear_empresa(session, 10, nif="A00000001", razon_social="Diez SL")
            await crear_empresa(session, 20, nif="B00000002", razon_social="Veinte SL")
            session.add(
                UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True)
            )
            await session.flush()
            otra_id = None
            for tenant, etiqueta in ((10, "Propia"), (20, "Otra")):
                ids: dict[str, int] = {}
                for codigo in ("4", "43", "430", "4300"):
                    cuenta = AccountPlan(
                        tenant_id=tenant, code=codigo, name=f"{etiqueta}-{codigo}",
                        parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
                        level=len(codigo), is_active=True, is_selectable=len(codigo) >= 4,
                    )
                    session.add(cuenta)
                    await session.flush()
                    ids[codigo] = cuenta.id
                if tenant == 20:
                    otra_id = ids["4300"]
            await session.commit()
        assert otra_id is not None
        return emit_token(1), otra_id

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        token, otra_id = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(informes_router)

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
        yield client, token, otra_id
    _cerrar(engine)


def _cerrar(engine) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def test_mayor_otra_empresa_404_sin_datos(api_client) -> None:
    client, token, otra_id = api_client
    resp = client.get(
        f"/api/v1/reports/ledger/{otra_id}",
        headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": "10"},
    )
    assert resp.status_code == 404
    assert "Otra" not in resp.text
