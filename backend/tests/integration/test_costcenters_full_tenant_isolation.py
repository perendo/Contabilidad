"""T044: Aislamiento completo multi-tenant + RBAC (SPEC-017, constitución III y SPEC-015).

Un usuario ADMIN de A no toca datos de B; un usuario READ_ONLY no puede
escribir en ninguno de los módulos de centros (403) pero sí leer lo suyo.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.costcenters.routes import router as costcenters_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.acct.seed import seed_default_pgc
from services.auth.security import emit_token, hash_password
from tests.conftest import crear_empresas


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


@pytest.fixture
def app_roles():
    import asyncio as _asyncio

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
                    User(id=1, email="admin@x.es", password_hash=hash_password("pw"), full_name="Admin"),
                    User(id=3, email="solo@x.es", password_hash=hash_password("pw"), full_name="ReadOnly"),
                ]
            )
            await crear_empresas(
                session, 10, 20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Diez", 20: "Veinte"},
            )
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=4, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            await session.flush()
            await seed_default_pgc(session, 10)
            await seed_default_pgc(session, 20)
            await session.commit()
        return emit_token(1), emit_token(3)

    loop = _asyncio.new_event_loop()
    try:
        token_admin, token_ro = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(costcenters_router)

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
        yield client, token_admin, token_ro

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def test_readonly_no_puede_crear_centro(app_roles):
    client, _, token_ro = app_roles
    r = client.post("/api/v1/centros", json={"codigo": "RO1", "nombre": "RO", "tipo": "proyecto"}, headers=_hh(token_ro, 10))
    assert r.status_code == 403


def test_readonly_no_puede_inactivar(app_roles):
    client, token_admin, token_ro = app_roles
    centro = client.post("/api/v1/centros", json={"codigo": "RO2", "nombre": "RO", "tipo": "proyecto"}, headers=_hh(token_admin, 10)).json()["id"]
    r = client.post(f"/api/v1/centros/{centro}/inactivar", headers=_hh(token_ro, 10))
    assert r.status_code == 403


def test_readonly_puede_ver_su_empresa(app_roles):
    client, token_admin, token_ro = app_roles
    client.post("/api/v1/centros", json={"codigo": "VIS", "nombre": "Visible", "tipo": "proyecto"}, headers=_hh(token_admin, 10))
    r = client.get("/api/v1/centros", headers=_hh(token_ro, 10))
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_admin_no_accede_a_datos_de_b(app_roles):
    client, token_admin, _ = app_roles
    centro_a = client.post("/api/v1/centros", json={"codigo": "AU", "nombre": "A", "tipo": "proyecto"}, headers=_hh(token_admin, 10)).json()["id"]

    # B no ve el centro de A
    r = client.get(f"/api/v1/centros/{centro_a}", headers=_hh(token_admin, 20))
    assert r.status_code == 404

    # B no puede editar el centro de A
    r = client.patch(f"/api/v1/centros/{centro_a}", json={"nombre": "Hacked"}, headers=_hh(token_admin, 20))
    assert r.status_code == 404

    # Listado de B vacío
    r = client.get("/api/v1/centros", headers=_hh(token_admin, 20))
    assert r.json()["total"] == 0
