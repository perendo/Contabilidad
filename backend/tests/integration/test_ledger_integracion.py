"""Tests SPEC-004 US2 (T026): mayor completo vía HTTP, A solo ve lo de A."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.journal.journal import router as journal_router
from api.reports.informes import router as informes_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.acct.account_plan import AccountPlan
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password
from tests.conftest import crear_empresas


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

    async def _setup() -> tuple[str, dict[str, int], dict[str, int]]:
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
            cuentas_a = await _pgc(session, 10)
            cuentas_b = await _pgc(session, 20)
            await session.commit()
        return emit_token(1), cuentas_a, cuentas_b

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        token, cuentas_a, cuentas_b = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(journal_router)
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
        yield client, token, cuentas_a, cuentas_b
    _cerrar(engine)


def _cerrar(engine) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _asentar(client, token, empresa, cuentas, fecha, debe_cta, haber_cta, importe):
    creado = client.post(
        "/api/v1/journal/entries",
        json={
            "fecha": fecha, "concepto": "M",
            "lineas": [
                {"account_id": cuentas[debe_cta], "debit": importe, "credit": "0"},
                {"account_id": cuentas[haber_cta], "debit": "0", "credit": importe},
            ],
        },
        headers=_hh(token, empresa),
    )
    assert creado.status_code == 201, creado.text
    asentado = client.post(
        f"/api/v1/journal/entries/{creado.json()['id']}/post", headers=_hh(token, empresa)
    )
    assert asentado.status_code == 200, asentado.text


def test_mayor_a_solo_movimientos_de_a(api_client) -> None:
    client, token, cuentas_a, cuentas_b = api_client
    _asentar(client, token, 10, cuentas_a, "2026-01-10", "4300", "5720", "100.0000")
    _asentar(client, token, 20, cuentas_b, "2026-01-11", "4300", "5720", "9999.0000")
    _asentar(client, token, 10, cuentas_a, "2026-02-10", "5720", "4300", "30.0000")
    resp = client.get(
        f"/api/v1/reports/ledger/{cuentas_a['4300']}", headers=_hh(token, 10)
    )
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["cuenta"]["code"] == "4300"
    assert [m["saldo_acumulado"] for m in cuerpo["movimientos"]] == ["100.0000", "70.0000"]
    assert cuerpo["saldo_final"] == "70.0000"
