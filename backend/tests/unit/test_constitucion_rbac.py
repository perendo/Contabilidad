"""Tests SPEC-003 Polish (T032): matriz constitucional de roles y contexto."""

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
from tests.conftest import crear_empresa


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

    async def _setup() -> dict[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="admin@x.es", password_hash=hash_password("pw"), full_name="Adm"),
                    User(id=2, email="cont@x.es", password_hash=hash_password("pw"), full_name="Con"),
                    User(id=3, email="lec@x.es", password_hash=hash_password("pw"), full_name="Lec"),
                ]
            )
            await crear_empresa(session, 10, nif="A00000001", razon_social="Diez SL")
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=3, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                ]
            )
            cuentas: dict[str, int] = {}
            for codigo, nombre in (
                ("4", "Clientes"), ("43", "CV"), ("430", "CE"), ("4300", "CD"),
                ("5", "Tesoreria"), ("57", "Bancos"), ("572", "Bcc"), ("5720", "Bcd"),
            ):
                nivel = len(codigo)
                padre = cuentas.get(codigo[:-1]) if len(codigo) > 1 else None
                cuentas[codigo] = await _sembrar(session, 10, codigo, nombre, nivel, padre)
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    tokens = anyio.run(_setup)

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
        yield client, tokens
    anyio.run(_dispose, engine)


async def _dispose(engine) -> None:
    await engine.dispose()


def _hh(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": "10"}


def test_sin_empresa_ningun_recurso_accesible(api_client) -> None:
    client, tokens = api_client
    auth = {"Authorization": f"Bearer {tokens['admin']}"}
    assert client.get("/api/v1/accounts/tree", headers=auth).status_code == 403
    assert client.get("/api/v1/journal/entries", headers=auth).status_code == 403
    assert client.post("/api/v1/accounts", json={}, headers=auth).status_code == 403


def test_read_only_jamas_escribe(api_client) -> None:
    client, tokens = api_client
    headers = _hh(tokens["readonly"])
    assert client.get("/api/v1/accounts/tree", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/v1/accounts", json={"code": "4400", "name": "X"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.patch("/api/v1/accounts/1", json={"name": "Y"}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/journal/entries",
            json={"fecha": "2026-01-15", "concepto": "X", "lineas": []},
            headers=headers,
        ).status_code
        == 403
    )


def test_admin_y_accountant_escriben(api_client) -> None:
    client, tokens = api_client
    padre = next(
        nodo["id"]
        for nodo in client.get(
            "/api/v1/accounts/tree", headers=_hh(tokens["admin"])
        ).json()["nodos"]
        if nodo["code"] == "4"
    )
    for rol, codigo in (("admin", "44"), ("accountant", "46")):
        resp = client.post(
            "/api/v1/accounts",
            json={"code": codigo, "name": f"Prov {rol}", "parent_id": padre},
            headers=_hh(tokens[rol]),
        )
        assert resp.status_code == 201, (rol, resp.status_code, resp.text)


# ---------------------------------------------------------------------------
# SPEC-015 Polish (T043): validacion constitucional del modulo de permisos.
# ---------------------------------------------------------------------------


def test_empresa_id_en_todas_las_tablas_rbac(rbac_client) -> None:
    from sqlalchemy import select

    from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso
    from models.rbac.matriz_permiso import MatrizPermiso
    from models.rbac.rol import Rol

    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "aprobar").status_code == 201

    async def _op(session):
        roles = (await session.scalars(select(Rol))).all()
        por_id = {int(r.id): int(r.empresa_id) for r in roles}
        filas = (await session.scalars(select(MatrizPermiso))).all()
        coherentes = all(por_id.get(int(f.rol_id)) == int(f.empresa_id) for f in filas)
        eventos = (await session.scalars(select(EventoAuditoriaAcceso))).all()
        return {int(r.empresa_id) for r in roles}, coherentes, {int(e.empresa_id) for e in eventos}

    roles, coherentes, eventos_emp = rbac.run(rbac.consultar(_op))
    assert roles == {10, 20}
    assert coherentes is True
    assert eventos_emp <= {10, 20}


def test_evento_auditoria_es_inmutable(rbac_client) -> None:
    import pytest
    from sqlalchemy import delete, select
    from sqlalchemy.exc import IntegrityError

    from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso

    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "aprobar").status_code == 201

    async def _leer(session):
        return await session.scalar(select(EventoAuditoriaAcceso).limit(1))

    evento = rbac.run(rbac.consultar(_leer))
    assert evento is not None

    async def _borrar(session):
        await session.execute(
            delete(EventoAuditoriaAcceso).where(EventoAuditoriaAcceso.id == evento.id)
        )

    with pytest.raises(IntegrityError):
        rbac.run(rbac.mutar(_borrar))


def test_concesion_no_altera_asientos(rbac_client) -> None:
    from sqlalchemy import func, select

    from models.acct.journal import JournalEntry

    rbac = rbac_client

    async def _contar(session):
        return await session.scalar(select(func.count()).select_from(JournalEntry))

    antes = rbac.run(rbac.consultar(_contar))
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    # conceder un permiso no crea ni modifica asientos (SPEC-002 intacto)
    assert rbac.run(rbac.consultar(_contar)) == antes
