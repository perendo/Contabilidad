"""Tests SPEC-003 Polish (T034): los 6 escenarios de quickstart.md vía HTTP."""

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
from api.auth.auth import router as auth_router
from api.companies import router as companies_router
from api.journal.journal import router as journal_router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import hash_password


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

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="contador@empresaa.es", password_hash=hash_password("Secret123!"), full_name="Contador"),
                    User(id=2, email="lector@empresaa.es", password_hash=hash_password("pw"), full_name="Lector"),
                    Company(company_id=10, nif="A00000001", razon_social="Empresa A SL"),
                    Company(company_id=20, nif="B00000002", razon_social="Empresa B SL"),
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                ]
            )
            await session.commit()

    anyio.run(_setup)

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(companies_router)
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
        yield client
    anyio.run(_dispose, engine)


async def _dispose(engine) -> None:
    await engine.dispose()


def _login(client: TestClient) -> tuple[str, int]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "contador@empresaa.es", "password": "Secret123!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_company_id"] == 10
    assert any(c["role"] == "ADMIN" for c in body["companies"])
    return body["token"], body["default_company_id"]


def test_s1_login_defecto(api_client) -> None:
    _login(api_client)
    resp = api_client.post(
        "/api/v1/auth/login",
        json={"email": "contador@empresaa.es", "password": "mala"},
    )
    assert resp.status_code == 401


def test_s2_crear_empresa_con_seed(api_client) -> None:
    client = api_client
    token, _ = _login(client)
    auth = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v1/companies",
        json={"nif": "A12345678", "razon_social": "Nueva Empresa S.L."},
        headers=auth,
    )
    assert resp.status_code == 201
    nueva = resp.json()["company_id"]
    assert resp.json()["role"] == "ADMIN"
    arbol = client.get(
        "/api/v1/accounts/tree",
        headers={**auth, "X-Empresa-Activa": str(nueva)},
    )
    assert arbol.status_code == 200
    assert len(arbol.json()["nodos"]) >= 7


def test_s3_switch_actualiza_contexto(api_client) -> None:
    client = api_client
    token, _ = _login(client)
    auth = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/auth/switch-company", json={"company_id": 20}, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["company_id"] == 20
    assert resp.json()["role"] == "ACCOUNTANT"
    arbol = client.get("/api/v1/accounts/tree", headers={**auth, "X-Empresa-Activa": "20"})
    assert arbol.status_code == 200


def test_s4_denegacion_sin_fugas(api_client) -> None:
    client = api_client
    token, _ = _login(client)
    auth = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/accounts/tree", headers={**auth, "X-Empresa-Activa": "999"})
    assert resp.status_code == 403
    assert "Empresa B" not in resp.text
    assert client.get("/api/v1/accounts/tree", headers=auth).status_code == 403


def test_s5_readonly_bloqueado_escritura(api_client) -> None:
    client = api_client
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "lector@empresaa.es", "password": "pw"},
    )
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}", "X-Empresa-Activa": "10"}
    assert client.get("/api/v1/accounts/tree", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/v1/accounts", json={"code": "4400", "name": "X"}, headers=headers
        ).status_code
        == 403
    )


def test_s6_aislamiento_completo(api_client) -> None:
    client = api_client
    token, _ = _login(client)
    auth = {"Authorization": f"Bearer {token}"}
    assert (
        client.post("/api/v1/auth/switch-company", json={"company_id": 999}, headers=auth).status_code
        == 403
    )
    for ruta, kwargs in [
        ("/api/v1/accounts/tree", {}),
        ("/api/v1/journal/entries", {"params": {"date_from": "2026-01-01", "date_to": "2026-12-31"}}),
    ]:
        resp = client.get(ruta, headers={**auth, "X-Empresa-Activa": "999"}, **kwargs)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# SPEC-015 Polish (T046): escenarios de
# specs/015-permisos-por-rol/quickstart.md reproducidos sobre `rbac_client`.
# El endpoint de ejemplo es el modulo `acct` (accounts); donde el quickstart
# usa `/asientos/{id}/aprobar` (no implementado) se prueba la operacion
# equivalente con un endpoint real.
# ---------------------------------------------------------------------------


def _padre_q(rbac):
    resp = rbac.get(10, "/api/v1/accounts/tree", "admin")
    pila = list(resp.json()["nodos"])
    while pila:
        nodo = pila.pop()
        if nodo["code"] == "430":
            return nodo["id"]
        pila.extend(nodo.get("children", []))
    raise AssertionError("cuenta 430 no encontrada")


def test_s1_catalogo_semilla(rbac_client) -> None:
    rbac = rbac_client
    data = rbac.get(10, "/api/v1/permisos/catalogo", "admin").json()
    modulos = {m["modulo"]: m["operaciones"] for m in data["modulos"]}
    assert "acct" in modulos
    assert {"ver", "crear", "editar", "aprobar", "importar_exportar", "configurar", "baja", "cerrar"} <= set(modulos["acct"])


def test_s1_matriz_seed_por_empresa(rbac_client) -> None:
    rbac = rbac_client
    items = rbac.get(10, "/api/v1/permisos/matriz", "admin").json()["items"]
    assert len(items) == 179
    assert all(i["rol"] in {"ADMIN", "ACCOUNTANT", "READ_ONLY"} for i in items)


def test_s2_denegacion_por_defecto_y_auditada(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post("/api/v1/accounts", 10, "readonly", json={"code": "4801", "name": "X"})
    assert resp.status_code == 403
    eventos = rbac.get(10, "/api/v1/permisos/auditoria", "admin", resultado="deny").json()
    assert eventos["total"] == 1
    evento = eventos["items"][0]
    assert (evento["modulo"], evento["operacion"], evento["motivo"]) == ("acct", "crear", "sin_permiso")
    assert evento["timestamp_utc"] and evento["ip"]


def test_s2_operacion_inexistente(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        10,
        "admin",
        json={"rol_id": rbac.resolver_rol(10, "READ_ONLY"), "modulo": "acct", "operacion": "aprobar_todo"},
    )
    assert resp.status_code == 422


def test_s3_concesion_auditada_y_revocacion_inmediata(rbac_client) -> None:
    rbac = rbac_client
    body = {"code": "4309", "name": "Concedida", "parent_id": _padre_q(rbac)}
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 201
    allow = rbac.get(10, "/api/v1/permisos/auditoria", "admin", resultado="allow", modulo="acct").json()
    assert allow["total"] >= 1

    matriz_id = rbac.matriz_id(10, "READ_ONLY", "acct", "crear")
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_id}", 10, "admin").status_code == 204
    assert rbac.post("/api/v1/accounts", 10, "readonly", json=body).status_code == 403


def test_s3_concesion_duplicada(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 409


def test_s4_matriz_aislada_por_empresa(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.get(10, "/api/v1/accounts/tree", "accountant").status_code == 200
    matriz_a = rbac.matriz_id(10, "ACCOUNTANT", "acct", "ver")
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_a}", 10, "admin").status_code == 204
    assert rbac.get(10, "/api/v1/accounts/tree", "accountant").status_code == 403
    assert rbac.get(20, "/api/v1/accounts/tree", "accountant").status_code == 200


def test_s4_sin_acceso_cross_tenant(rbac_client) -> None:
    rbac = rbac_client
    matriz_b = rbac.matriz_id(20, "READ_ONLY", "acct", "ver")
    assert rbac.delete(f"/api/v1/permisos/matriz/{matriz_b}", 10, "admin").status_code == 404


def test_s5_mis_permisos_por_empresa(rbac_client) -> None:
    rbac = rbac_client
    propios = rbac.get(10, "/api/v1/permisos/mis-permisos", "readonly").json()
    assert propios["rol"] == "READ_ONLY"
    assert all(p["operacion"] == "ver" for p in propios["permisos"])
    # no incluye las concesiones de ACCOUNTANT ni las de B
    assert ("acct", "crear") not in {(p["modulo"], p["operacion"]) for p in propios["permisos"]}


def test_s6_admin_sin_privilegio_global(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        20,
        "admin",
        json={"rol_id": rbac.resolver_rol(10, "READ_ONLY"), "modulo": "acct", "operacion": "aprobar"},
    )
    assert resp.status_code == 422
