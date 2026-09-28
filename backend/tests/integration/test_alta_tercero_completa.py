"""Tests SPEC-008 US1 (T025/T026): alta de tercero vía HTTP y aislamiento."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.thirdparty import router as thirdparty_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.acct.seed import seed_default_pgc
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
                session, 10, 20,
                nifs={10: "A00000001", 20: "B00000002"},
                razones_sociales={10: "Diez SL", 20: "Veinte SL"},
            )
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                ]
            )
            await session.flush()
            await seed_default_pgc(session, 10)
            await seed_default_pgc(session, 20)
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(thirdparty_router)

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
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_alta_via_http_con_subcuentas_y_auditoria(api_client) -> None:
    client, token, _ = api_client
    resp = client.post(
        "/api/v1/terceros",
        json={
            "nif": "12345678Z",
            "razon_social": "Cliente A SL",
            "es_cliente": True,
            "es_proveedor": True,
            "iban": "ES9121000418450200051332",
        },
        headers=_hh(token, 10),
    )
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert cuerpo["nif"] == "12345678Z"
    assert cuerpo["iban"] == "ES9121000418450200051332"
    detalle = client.get(f"/api/v1/terceros/{cuerpo['id']}", headers=_hh(token, 10))
    assert detalle.status_code == 200
    assert {s["tipo"] for s in detalle.json()["saldo"]["subcuentas"]} == {
        "CLIENTE",
        "PROVEEDOR",
    }


def test_alta_nif_invalido_422(api_client) -> None:
    client, token, _ = api_client
    resp = client.post(
        "/api/v1/terceros",
        json={"nif": "12345678A", "razon_social": "X", "es_cliente": True},
        headers=_hh(token, 10),
    )
    assert resp.status_code == 422


def test_aislamiento_alta_entre_empresas(api_client) -> None:
    client, token, _ = api_client
    a = client.post(
        "/api/v1/terceros",
        json={"nif": "12345678Z", "razon_social": "A", "es_cliente": True},
        headers=_hh(token, 10),
    )
    assert a.status_code == 201
    # Mismo NIF en otra empresa: ficha separada
    b = client.post(
        "/api/v1/terceros",
        json={"nif": "12345678Z", "razon_social": "B", "es_cliente": True},
        headers=_hh(token, 20),
    )
    assert b.status_code == 201
    assert client.get(f"/api/v1/terceros/{a.json()['id']}", headers=_hh(token, 20)).status_code == 404
    assert client.get("/api/v1/terceros", headers=_hh(token, 20)).json()["total"] == 1
