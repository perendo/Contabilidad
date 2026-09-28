"""Tests SPEC-003 Polish (T033): dos empresas completas, cruces múltiples → 403/404."""

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
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password


async def _sembrar(
    db: AsyncSession, tenant_id: int, codigo: str, nombre: str, nivel: int, padre: int | None
) -> int:
    cuenta = AccountPlan(
        tenant_id=tenant_id, code=codigo, name=nombre,
        parent_id=padre, level=nivel, is_active=True,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta.id


async def _plantar(db: AsyncSession, tenant_id: int, etiqueta: str) -> dict[str, int]:
    cuentas: dict[str, int] = {}
    for codigo, nombre in (
        ("4", f"Clientes {etiqueta}"), ("43", "CV"), ("430", "CE"), ("4300", "CD"),
        ("5", f"Tesoreria {etiqueta}"), ("57", "Bancos"), ("572", "Bcc"), ("5720", "Bcd"),
    ):
        nivel = len(codigo)
        padre = cuentas.get(codigo[:-1]) if len(codigo) > 1 else None
        cuentas[codigo] = await _sembrar(db, tenant_id, codigo, nombre, nivel, padre)
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

    async def _setup() -> tuple[str, str, dict[str, int], dict[str, int]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana"),
                    User(id=2, email="luis@x.es", password_hash=hash_password("pw"), full_name="Luis"),
                    Company(company_id=10, nif="A00000001", razon_social="Diez SL"),
                    Company(company_id=20, nif="B00000002", razon_social="Veinte SL"),
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=2, company_id=20, role=UserRol.ADMIN, is_default=True),
                ]
            )
            await session.flush()
            cuentas_a = await _plantar(session, 10, "A")
            cuentas_b = await _plantar(session, 20, "B")
            await session.commit()
        return emit_token(1), emit_token(2), cuentas_a, cuentas_b

    token_a, token_b, cuentas_a, cuentas_b = anyio.run(_setup)

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

    def _lineas(cuentas: dict[str, int]) -> list[dict]:
        return [
            {"account_id": cuentas["4300"], "debit": "50.0000", "credit": "0", "detail": "c"},
            {"account_id": cuentas["5720"], "debit": "0", "credit": "50.0000", "detail": "b"},
        ]

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        ids = {}
        for nombre, token, emp, cuentas in (
            ("a", token_a, 10, cuentas_a),
            ("b", token_b, 20, cuentas_b),
        ):
            resp = client.post(
                "/api/v1/journal/entries",
                json={"fecha": "2026-02-01", "concepto": f"Vta {nombre}", "lineas": _lineas(cuentas)},
                headers={"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(emp)},
            )
            assert resp.status_code == 201
            ids[nombre] = resp.json()["id"]
        yield client, token_a, token_b, cuentas_a, cuentas_b, ids
    anyio.run(_dispose, engine)


async def _dispose(engine) -> None:
    await engine.dispose()


def test_cruces_multiples_sin_fugas(api_client) -> None:
    client, token_a, token_b, cuentas_a, cuentas_b, ids = api_client
    fugas = ("Diez", "Veinte", "A00000001", "B00000002")
    casos = [
        (token_a, 20, "GET", "/api/v1/accounts/tree", {}),
        (token_a, 20, "GET", "/api/v1/accounts/suggest", {"params": {"q": "43"}}),
        (token_a, 20, "GET", f"/api/v1/accounts/{cuentas_b['4300']}", {}),
        (token_a, 20, "POST", "/api/v1/accounts", {"json": {"code": "44", "name": "X"}}),
        (token_b, 10, "GET", "/api/v1/accounts/tree", {}),
        (token_b, 10, "GET", f"/api/v1/accounts/{cuentas_a['4300']}", {}),
        (token_b, 10, "POST", "/api/v1/accounts", {"json": {"code": "44", "name": "X"}}),
        (token_a, 20, "GET", "/api/v1/journal/entries", {"params": {"date_from": "2026-01-01", "date_to": "2026-12-31"}}),
        (token_a, 20, "GET", f"/api/v1/journal/entries/{ids['b']}", {}),
        (token_a, 20, "POST", f"/api/v1/journal/entries/{ids['b']}/reverse", {"json": {}}),
        (token_b, 10, "GET", "/api/v1/journal/entries", {"params": {"date_from": "2026-01-01", "date_to": "2026-12-31"}}),
        (token_b, 10, "GET", f"/api/v1/journal/entries/{ids['a']}", {}),
        (token_b, 10, "POST", f"/api/v1/journal/entries/{ids['a']}/reverse", {"json": {}}),
    ]
    for token, empresa, method, ruta, kwargs in casos:
        headers = {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}
        resp = getattr(client, method.lower())(ruta, headers=headers, **kwargs)
        assert resp.status_code in (403, 404), (ruta, empresa, resp.status_code)
        assert not any(f in resp.text for f in fugas), (ruta, empresa)


# ---------------------------------------------------------------------------
# SPEC-015 Polish (T044): aislamiento cross-empresa completo (matriz + auditoria)
# ---------------------------------------------------------------------------


def test_concesion_en_a_no_toca_la_matriz_de_b(rbac_client) -> None:
    from sqlalchemy import func, select

    from models.rbac.matriz_permiso import MatrizPermiso

    rbac = rbac_client

    async def _contar(session, empresa_id):
        return await session.scalar(
            select(func.count()).select_from(MatrizPermiso).where(MatrizPermiso.empresa_id == empresa_id)
        )

    async def _counts(session):
        return await _contar(session, 10), await _contar(session, 20)

    antes = rbac.run(rbac.consultar(_counts))
    assert rbac.conceder(10, "READ_ONLY", "acct", "aprobar").status_code == 201
    despues = rbac.run(rbac.consultar(_counts))
    assert despues[0] == antes[0] + 1
    assert despues[1] == antes[1]


def test_evento_de_a_invisible_para_b(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.post("/api/v1/accounts", 10, "readonly", json={"code": "4901", "name": "X"}).status_code == 403
    assert rbac.get(10, "/api/v1/permisos/auditoria", "admin").json()["total"] == 1
    assert rbac.get(20, "/api/v1/permisos/auditoria", "admin").json()["total"] == 0


def test_rol_de_a_no_actua_en_b_sin_concesion(rbac_client) -> None:
    from sqlalchemy import delete

    from models.rbac.matriz_permiso import MatrizPermiso

    rbac = rbac_client

    async def _vaciar_b(session):
        await session.execute(delete(MatrizPermiso).where(MatrizPermiso.empresa_id == 20))

    rbac.run(rbac.mutar(_vaciar_b))
    # la misma cuenta (ACCOUNTANT) con el mismo vinculo: en A ok, en B denegado
    assert rbac.get(10, "/api/v1/accounts/tree", "accountant").status_code == 200
    assert rbac.get(20, "/api/v1/accounts/tree", "accountant").status_code == 403
