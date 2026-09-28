"""Tests SPEC-003 US3 (T026): usuario B contra recursos de A → 403/404 siempre."""

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


async def _sembrar_cuenta(
    db: AsyncSession, tenant_id: int, codigo: str, nombre: str, nivel: int, padre: int | None
) -> int:
    cuenta = AccountPlan(
        tenant_id=tenant_id, code=codigo, name=nombre,
        parent_id=padre, level=nivel, is_active=True,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta.id


async def _plantar_pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    cuentas: dict[str, int] = {}
    for codigo, nombre in (
        ("4", "Clientes"), ("43", "Clientes varios"), ("430", "Clientes emisores"),
        ("4300", "Clientes detalle"), ("5", "Tesoreria"), ("57", "Bancos"),
        ("572", "Bancos c/c"), ("5720", "Bancos c/c detalle"),
    ):
        nivel = len(codigo)
        padre = cuentas.get(codigo[:-1]) if len(codigo) > 1 else None
        cuentas[codigo] = await _sembrar_cuenta(db, tenant_id, codigo, nombre, nivel, padre)
    return cuentas


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

    async def _setup() -> tuple[str, str, dict[str, int], str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            session.add(
                User(id=2, email="luis@x.es", password_hash=hash_password("pw"), full_name="Luis")
            )
            await crear_empresas(
                session, 10, 20,
                nifs={10: "A00000001", 20: "B00000002"},
                razones_sociales={10: "Diez SL", 20: "Veinte SL"},
            )
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=2, company_id=20, role=UserRol.ACCOUNTANT, is_default=True),
                ]
            )
            await session.flush()
            cuentas = await _plantar_pgc(session, 10)
            await _plantar_pgc(session, 20)
            await session.commit()
        return emit_token(1), emit_token(2), cuentas, ""

    token_a, token_b, cuentas_a, _ = anyio.run(_setup)

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
        lineas = [
            {"account_id": cuentas_a["4300"], "debit": "100.0000", "credit": "0", "detail": "c"},
            {"account_id": cuentas_a["5720"], "debit": "0", "credit": "100.0000", "detail": "b"},
        ]
        creado = client.post(
            "/api/v1/journal/entries",
            json={"fecha": "2026-01-15", "concepto": "Venta", "lineas": lineas},
            headers={"Authorization": f"Bearer {token_a}", "X-Empresa-Activa": "10"},
        )
        assert creado.status_code == 201
        yield client, token_a, token_b, cuentas_a, creado.json()["id"]
    anyio.run(_dispose, engine)


async def _dispose(engine) -> None:
    await engine.dispose()


def _hb(token_b: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_b}", "X-Empresa-Activa": "10"}


def test_b_contra_recursos_de_a_todo_denegado(api_client) -> None:
    client, _, token_b, cuentas_a, entry_id = api_client
    casos = [
        ("GET", "/api/v1/accounts/tree", {}),
        ("GET", "/api/v1/accounts/suggest", {"params": {"q": "43"}}),
        ("GET", f"/api/v1/accounts/{cuentas_a['4300']}", {}),
        ("POST", "/api/v1/accounts", {"json": {"code": "4400", "name": "X"}}),
        ("GET", "/api/v1/journal/entries", {"params": {"date_from": "2026-01-01", "date_to": "2026-12-31"}}),
        ("GET", f"/api/v1/journal/entries/{entry_id}", {}),
        ("POST", "/api/v1/journal/entries", {"json": {"fecha": "2026-01-15", "concepto": "X", "lineas": []}}),
        ("POST", f"/api/v1/journal/entries/{entry_id}/reverse", {"json": {}}),
    ]
    for method, ruta, kwargs in casos:
        resp = getattr(client, method.lower())(ruta, headers=_hb(token_b), **kwargs)
        assert resp.status_code in (403, 404), (method, ruta, resp.status_code)
        assert "Diez" not in resp.text


def test_cuenta_de_a_invisible_desde_empresa_propia_de_b(api_client) -> None:
    client, _, token_b, cuentas_a, _ = api_client
    resp = client.get(
        f"/api/v1/accounts/{cuentas_a['4300']}",
        headers={"Authorization": f"Bearer {token_b}", "X-Empresa-Activa": "20"},
    )
    assert resp.status_code == 404
