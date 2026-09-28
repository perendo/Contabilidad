"""Tests SPEC-004 Polish (T049): los 6 escenarios de quickstart.md vía HTTP."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.journal.journal import router as journal_router
from api.reports.fiscal import router as fiscal_router
from api.reports.informes import router as informes_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password


async def _pgc(db: AsyncSession, tenant_id: int, etiqueta: str) -> dict[str, int]:
    ids: dict[str, int] = {}
    for codigo in (
        "1", "12", "129", "5", "57", "572", "5720",
        "6", "60", "600", "6000", "7", "70", "700", "7000",
    ):
        cuenta = AccountPlan(
            tenant_id=tenant_id, code=codigo, name=f"{etiqueta}-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=True,
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

    async def _setup() -> tuple[str, str, dict[str, int], dict[str, int]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="a@test.es", password_hash=hash_password("pw"), full_name="A"),
                    User(id=2, email="b@test.es", password_hash=hash_password("pw"), full_name="B"),
                    Company(company_id=10, nif="A00000001", razon_social="Diez SL"),
                    Company(company_id=20, nif="B00000002", razon_social="Veinte SL"),
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=2, company_id=20, role=UserRol.ADMIN, is_default=True),
                    FiscalYear(
                        empresa_id=10, year=2026,
                        date_start=date(2026, 1, 1),
                        date_end=date(2026, 12, 31),
                    ),
                ]
            )
            await session.flush()
            cuentas_a = await _pgc(session, 10, "A")
            cuentas_b = await _pgc(session, 20, "B")
            await session.commit()
        return emit_token(1), emit_token(2), cuentas_a, cuentas_b

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        token_a, token_b, cuentas_a, cuentas_b = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(journal_router)
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
        yield client, token_a, token_b, cuentas_a, cuentas_b, factory
    _cerrar(engine)


def _cerrar(engine) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


def _ha(token_a: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_a}", "X-Empresa-Activa": "10"}


def _hb(token_b: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_b}", "X-Empresa-Activa": "10"}


def _asentar(client, token, empresa, cuentas, debe, haber, importe, fecha="2026-05-01"):
    creado = client.post(
        "/api/v1/journal/entries",
        json={
            "fecha": fecha, "concepto": "Op",
            "lineas": [
                {"account_id": cuentas[debe], "debit": importe, "credit": "0"},
                {"account_id": cuentas[haber], "debit": "0", "credit": importe},
            ],
        },
        headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)},
    )
    assert creado.status_code == 201, creado.text
    asentado = client.post(
        f"/api/v1/journal/entries/{creado.json()['id']}/post",
        headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)},
    )
    assert asentado.status_code == 200, asentado.text


def test_s1_balance_cuadra(api_client) -> None:
    client, token_a, _, cuentas_a, _, _ = api_client
    _asentar(client, token_a, 10, cuentas_a, "6000", "5720", "100.0000")
    resp = client.get(
        "/api/v1/reports/trial-balance",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31", "level": 4},
        headers=_ha(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["cuadra"] is True
    assert resp.json()["total_debe"] == resp.json()["total_haber"]


def test_s2_mayor_saldo_acumulado(api_client) -> None:
    client, token_a, _, cuentas_a, _, _ = api_client
    _asentar(client, token_a, 10, cuentas_a, "6000", "5720", "100.0000")
    resp = client.get(
        f"/api/v1/reports/ledger/{cuentas_a['6000']}", headers=_ha(token_a)
    )
    assert resp.status_code == 200
    assert resp.json()["saldo_final"] == "100.0000"
    assert client.get("/api/v1/reports/ledger/999999", headers=_ha(token_a)).status_code == 404


def test_s3_cierre_atomico_y_bloqueo(api_client) -> None:
    client, token_a, _, cuentas_a, _, _ = api_client
    _asentar(client, token_a, 10, cuentas_a, "6000", "5720", "100.0000")
    cierre = client.post("/api/v1/fiscal-years/2026/close", headers=_ha(token_a))
    assert cierre.status_code == 200
    assert cierre.json()["is_closed"] is True
    assert cierre.json()["regularizacion_entry_id"] is not None
    tarde = client.post(
        "/api/v1/journal/entries",
        json={
            "fecha": "2026-11-15", "concepto": "X",
            "lineas": [
                {"account_id": cuentas_a["6000"], "debit": "1.0000", "credit": "0"},
                {"account_id": cuentas_a["5720"], "debit": "0", "credit": "1.0000"},
            ],
        },
        headers=_ha(token_a),
    )
    assert tarde.status_code == 400


def test_s4_doble_cierre_409(api_client) -> None:
    client, token_a, _, _, _, _ = api_client
    assert client.post("/api/v1/fiscal-years/2026/close", headers=_ha(token_a)).status_code == 200
    assert client.post("/api/v1/fiscal-years/2026/close", headers=_ha(token_a)).status_code == 409


def test_s5_facturas_sin_api(api_client) -> None:
    import asyncio

    from models.ar.invoice import InvoiceTipo
    from services.invoicing.invoice_service import crear_factura

    _, _, _, _, _, factory = api_client

    async def _crear() -> tuple:
        async with factory() as session:
            emitida = await crear_factura(
                session, empresa_id=10, tipo=InvoiceTipo.emitida, ejercicio=2026,
                nif_tercero="A11111111", fecha=date(2026, 1, 15),
                base="100.0000", cuota_iva="21.0000", actor="test",
            )
            recibida = await crear_factura(
                session, empresa_id=10, tipo=InvoiceTipo.recibida, ejercicio=2026,
                nif_tercero="B22222222", fecha=date(2026, 1, 16),
                base="50.0000", cuota_iva="10.5000", actor="test",
            )
            await session.commit()
            return emitida, recibida

    loop = asyncio.new_event_loop()
    try:
        emitida, recibida = loop.run_until_complete(_crear())
    finally:
        loop.close()
    assert (emitida.numero_seq, recibida.numero_seq) == (1, 2)
    assert f"{emitida.total:0.4f}" == "121.0000"


def test_s6_aislamiento_informes_y_cierre(api_client) -> None:
    client, _, token_b, _, _, _ = api_client
    assert (
        client.get(
            "/api/v1/reports/trial-balance",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_hb(token_b),
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/fiscal-years/2026/close", headers=_hb(token_b)).status_code
        == 403
    )
