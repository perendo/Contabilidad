"""Tests SPEC-003 US3 (T024): contexto ausente o malformado → denegado sin oráculo."""

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

    async def _setup() -> tuple[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            session.add(
                User(
                    id=2, email="bloq@x.es", password_hash=hash_password("pw"),
                    full_name="Bloq", is_active=False,
                )
            )
            await crear_empresas(
                session, 10, 20,
                nifs={10: "A00000001", 20: "B00000002"},
                razones_sociales={10: "Diez SL", 20: "Veinte SL"},
                inactivos=(20,),
            )
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                ]
            )
            await session.commit()
        return emit_token(1), emit_token(2)

    token, token_bloq = anyio.run(_setup)

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
        yield client, token, token_bloq
    anyio.run(_dispose, engine)


async def _dispose(engine) -> None:
    await engine.dispose()


def test_sin_cabecera_empresa_403(api_client) -> None:
    client, token, _ = api_client
    for ruta in ("/api/v1/accounts/tree", "/api/v1/journal/entries"):
        resp = client.get(ruta, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, (ruta, resp.status_code)


def test_cabecera_malformada_403(api_client) -> None:
    client, token, _ = api_client
    for valor in ("abc", "0", "-5"):
        resp = client.get(
            "/api/v1/accounts/tree",
            headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": valor},
        )
        assert resp.status_code == 403, (valor, resp.status_code)


def test_inexistente_y_sin_permiso_mismo_mensaje(api_client) -> None:
    client, token, _ = api_client
    sin_permiso = client.get(
        "/api/v1/accounts/tree",
        headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": "999"},
    )
    assert sin_permiso.status_code == 403
    assert "Diez" not in sin_permiso.text
    inactiva = client.get(
        "/api/v1/accounts/tree",
        headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": "20"},
    )
    assert inactiva.status_code == 403
    assert inactiva.json()["detail"] == sin_permiso.json()["detail"]


def test_usuario_inactivo_denegado_sin_fugas(api_client) -> None:
    client, _, token_bloq = api_client
    resp = client.get(
        "/api/v1/accounts/tree",
        headers={"Authorization": f"Bearer {token_bloq}", "X-Empresa-Activa": "10"},
    )
    assert resp.status_code in (401, 403)
    assert "Diez" not in resp.text
