"""Tests SPEC-001 US4 (T036): desactivar cuenta con imputaciones → 409 intacta."""

from __future__ import annotations

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
from tests.conftest import crear_empresa


async def _pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    ids: dict[str, int] = {}
    for codigo in ("4", "43", "430", "4300", "5", "57", "572", "5720"):
        cuenta = AccountPlan(
            tenant_id=tenant_id, code=codigo, name=f"C-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=len(codigo) >= 4,
        )
        db.add(cuenta)
        await db.flush()
        ids[codigo] = cuenta.id
    return ids


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

    async def _setup() -> tuple[str, dict[str, int]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await crear_empresa(session, 10, nif="A00000001", razon_social="Diez SL")
            session.add(
                UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True)
            )
            await session.flush()
            cuentas = await _pgc(session, 10)
            await session.commit()
        return emit_token(1), cuentas

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        token, cuentas = loop.run_until_complete(_setup())
    finally:
        loop.close()

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
        yield client, token, cuentas, factory
    _cerrar(engine)


def _cerrar(engine) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def _hh(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": "10"}


def test_desactivar_cuenta_con_imputaciones_409_intacta(api_client) -> None:
    client, token, cuentas, factory = api_client
    creado = client.post(
        "/api/v1/journal/entries",
        json={
            "fecha": "2026-05-01", "concepto": "V",
            "lineas": [
                {"account_id": cuentas["4300"], "debit": "10.0000", "credit": "0"},
                {"account_id": cuentas["5720"], "debit": "0", "credit": "10.0000"},
            ],
        },
        headers=_hh(token),
    )
    assert creado.status_code == 201
    assert client.post(
        f"/api/v1/journal/entries/{creado.json()['id']}/post", headers=_hh(token)
    ).status_code == 200

    resp = client.patch(
        f"/api/v1/accounts/{cuentas['4300']}",
        json={"is_active": False},
        headers=_hh(token),
    )
    assert resp.status_code == 409

    async def _activa() -> bool:
        async with factory() as session:
            cuenta = await session.get(AccountPlan, cuentas["4300"])
            assert cuenta is not None
            return cuenta.is_active

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        sigue_activa = loop.run_until_complete(_activa())
    finally:
        loop.close()
    assert sigue_activa is True
