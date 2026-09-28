"""Tests SPEC-013 (T035/T047/T050/T051): flujo HTTP de conciliación."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.reconciliation import router as reconciliation_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.acct.seed import seed_default_pgc
from services.auth.security import emit_token, hash_password

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def recon_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
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
                    User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana"),
                    Company(company_id=10, nif="A00000001", razon_social="Diez SL"),
                    Company(company_id=20, nif="B00000002", razon_social="Veinte SL"),
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
    app.include_router(reconciliation_router)

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


def _subir(client, token, empresa, nombre="extracto_43_19_valido.txt", cuenta="5720"):
    return client.post(
        "/api/v1/extractos",
        files={"file": (nombre, (FIXTURES / nombre).read_bytes(), "text/plain")},
        data={"layout": "norma_43_1919", "cuenta": cuenta},
        headers=_hh(token, empresa),
    )


def test_flujo_http_importar_conciliar_cerrar(recon_client) -> None:
    client, token, _ = recon_client
    resp = _subir(client, token, 10)
    assert resp.status_code == 201, resp.text
    extracto = resp.json()
    assert extracto["n_movimientos"] == 3

    # Reimportar → 409
    assert _subir(client, token, 10).status_code == 409

    # Listar
    assert client.get("/api/v1/extractos", headers=_hh(token, 10)).json()["total"] == 1

    # Abrir conciliación
    conc = client.post(
        "/api/v1/conciliaciones",
        json={"cuenta_id": extracto["cuenta_id"], "fecha_inicio": "2026-09-01",
              "fecha_fin": "2026-09-30", "extracto_id": extracto["id"]},
        headers=_hh(token, 10),
    )
    assert conc.status_code == 201, conc.text
    cid = conc.json()["id"]

    # Informe
    informe = client.get(f"/api/v1/conciliaciones/{cid}", headers=_hh(token, 10))
    assert informe.status_code == 200
    assert informe.json()["saldo_banco"] == "1105.0000"


def test_aislamiento_extracto_otra_empresa(recon_client) -> None:
    client, token, _ = recon_client
    creado = _subir(client, token, 10).json()
    assert client.get(f"/api/v1/extractos/{creado['id']}", headers=_hh(token, 20)).status_code == 404
    # La empresa A no puede importar una cuenta inexistente en su plan
    resp = _subir(client, token, 10, nombre="extracto_43_19_otra_empresa.txt", cuenta="")
    assert resp.status_code in (404, 422)
