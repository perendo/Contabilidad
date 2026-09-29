"""Shared pytest fixtures: in-memory SQLite async engine for treasury/journal tests."""

from __future__ import annotations

import asyncio
import types

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.journal.journal import router as journal_router
from api.treasury.routes import router
from base import Base
from database import get_db
from db.triggers import instalar_triggers_sqlite
from models.acct.account_plan import AccountPlan
from models.fiscal.ejercicio import (
    EjercicioContable,
    EjercicioEstado,
)
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password


async def crear_empresa(
    db: AsyncSession,
    empresa_id: int,
    *,
    nif: str | None = None,
    razon_social: str | None = None,
    is_active: bool = True,
) -> Company:
    """Crea la empresa **sin** plan de cuentas y la devuelve.

    Punto unico del repositorio para dar de alta una empresa en un test. Antes
    cada fichero repetia `db.add(Company(...)); await db.flush()`, con un NIF y
    una razon social inventados que ningun test miraba: 310 construcciones de
    `Company` y medio-update de variantes para el mismo hecho.

    `nif` y `razon_social` se derivan de `empresa_id` y por eso son deterministas
    y distintos entre empresas, que es lo que evita colisiones. Se pueden pasar
    explicitamente solo cuando el test **afirma** sobre ellos (por ejemplo
    `test_switch_company` compara la razon social que devuelve la API).

    Se hace `flush()` y no `commit()`: el commit sigue belonging a quien llama,
    y sin el flush la fila no existe todavia para el trigger de seeding del
    catalogo RBAC ni para las FKs del plan de cuentas.
    """
    empresa = Company(
        company_id=empresa_id,
        nif=nif if nif is not None else f"T{empresa_id:08d}",
        razon_social=razon_social if razon_social is not None else f"E{empresa_id} SL",
        is_active=is_active,
    )
    db.add(empresa)
    await db.flush()
    return empresa


async def sembrar_empresa_pgc(
    db: AsyncSession,
    empresa_id: int,
    *,
    nif: str | None = None,
    razon_social: str | None = None,
    is_active: bool = True,
) -> Company:
    """Crea la empresa y siembra su PGC base de 7 grupos (SPEC-001).

    Es la forma habitual de partir en un test: empresa + plan por defecto. Para
    una empresa sin plan, `crear_empresa`; para varias de golpe,
    `sembrar_empresas_pgc`.
    """
    from services.acct.seed import seed_default_pgc

    empresa = await crear_empresa(
        db, empresa_id, nif=nif, razon_social=razon_social, is_active=is_active
    )
    await seed_default_pgc(db, empresa_id)
    return empresa


async def crear_empresas(
    db: AsyncSession,
    *empresa_ids: int,
    nifs: dict[int, str] | None = None,
    razones_sociales: dict[int, str] | None = None,
    inactivos: tuple[int, ...] = (),
) -> dict[int, Company]:
    """Varias empresas **sin** plan de cuentas, en el orden indicado.

    Para los tests que plantan su propio plan a medida (`_plantar_pgc` y
    similares) en vez de usar el seed de 7 grupos. Sembrar el PGC estandar y
    luego plantar cuentas encima choca con `UNIQUE (tenant_id, code)`, asi que
    estos sitios NO pueden pasar por `sembrar_empresas_pgc`.
    """
    empresas: dict[int, Company] = {}
    for empresa_id in empresa_ids:
        empresas[empresa_id] = await crear_empresa(
            db,
            empresa_id,
            nif=(nifs or {}).get(empresa_id),
            razon_social=(razones_sociales or {}).get(empresa_id),
            is_active=empresa_id not in inactivos,
        )
    return empresas


async def sembrar_empresas_pgc(
    db: AsyncSession,
    *empresa_ids: int,
    nifs: dict[int, str] | None = None,
    razones_sociales: dict[int, str] | None = None,
    inactivos: tuple[int, ...] = (),
) -> dict[int, Company]:
    """Siembra varias empresas con su PGC base, en el orden indicado.

    Existe porque el par A=10 / B=20 se repite en mas de veinte fixtures y cada
    uno repetia el `add_all([...])` de las dos empresas mas el bucle de
    `seed_default_pgc`. El `flush` va **dentro** de `sembrar_empresa_pgc`, entre
    empresa y empresa, porque tanto el seed del plan como el trigger del catalogo
    RBAC necesitan ver la fila de la empresa.

    El NIF y la razon social se derivan de `empresa_id` y no se pasan: los que
    tenian los fixtures ("A00000001", "Diez SL"...) no los miraba ningun test, y
    mantenerlos obligaba a acarrearlos por todo el repositorio. Solo se aceptan
    `nifs` y `razones_sociales` para los casos en que un test **afirma** sobre
    el valor devuelto por la API o grabado en un modelo.
    """
    empresas: dict[int, Company] = {}
    for empresa_id in empresa_ids:
        empresas[empresa_id] = await sembrar_empresa_pgc(
            db,
            empresa_id,
            nif=(nifs or {}).get(empresa_id),
            razon_social=(razones_sociales or {}).get(empresa_id),
            is_active=empresa_id not in inactivos,
        )
    return empresas


@pytest.fixture
async def db_session_factory():
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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(instalar_triggers_sqlite)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def db_session(db_session_factory):
    async with db_session_factory() as session:
        yield session


@pytest.fixture
def client(db_session_factory):
    async def _sembrar_auth() -> str:
        async with db_session_factory() as session:
            session.add(
                User(id=99, email="tesoreria@x.es", password_hash=hash_password("pw"), full_name="Teso")
            )
            for cid in (42, 43, 44, 52, 53):
                session.add(
                    Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"Empresa {cid} SL")
                )
            await session.flush()
            for rid, cid in enumerate((42, 43, 44, 52, 53), start=100):
                session.add(
                    UserCompany(id=rid, user_id=99, company_id=cid, role=UserRol.ADMIN, is_default=(cid == 42))
                )
            await session.commit()
        return emit_token(99)

    token = _correr(_sembrar_auth())

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    state = {"empresa_id": 42}

    def _hh(empresa_id: int | None = None) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id if empresa_id is not None else state["empresa_id"]),
        }

    return _ClienteAutenticado(TestClient(app), _hh), state, {"token": token, "hh": _hh}


class _ClienteAutenticado:
    """Proxy de TestClient que inyecta Authorization + X-Empresa-Activa.

    Lee la empresa activa de `state` en cada petición (los tests la mutan
    para simular el cambio de empresa); unos headers explícitos siempre
    tienen prioridad sobre los inyectados.
    """

    def __init__(self, cliente: TestClient, hh) -> None:
        self._cliente = cliente
        self._hh = hh

    def __getattr__(self, nombre: str):
        atributo = getattr(self._cliente, nombre)
        if not callable(atributo) or nombre.startswith("_"):
            return atributo

        def _llamada(*args, **kwargs):
            kwargs.setdefault("headers", self._hh())
            return atributo(*args, **kwargs)

        return _llamada


@pytest.fixture
def terceros_client():
    """HTTP client con terceros + PGC sembrado en empresas A=10 y B=20."""
    import asyncio

    from api.thirdparty import router as thirdparty_router
    from api.treasury.tercero_amend import router as tercero_amend_router

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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(thirdparty_router)
    app.include_router(tercero_amend_router, prefix="/api/v1")

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


@pytest.fixture
def importexport_client():
    """HTTP client de import/export con journal y PGC en empresas A=10 y B=20."""
    import asyncio

    from api.importexport import router as importexport_router
    from api.journal.journal import router as journal_router

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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(importexport_router)
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
        yield client, token, factory
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()



@pytest.fixture
def ciclo_client():
    """HTTP client de apertura (SPEC-009) con PGC completo en A=10 y B=20."""
    import asyncio

    from api.ciclo.routes import router as ciclo_router

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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(ciclo_router)

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


def _correr(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def retenciones_client():
    import asyncio
    import types
    import uuid

    from api.fiscal.routes_retenciones import router as retenciones_router
    from models.ar.tercero import Tercero
    from models.ar.tercero_subcuenta import TerceroSubcuenta, TipoSubcuenta
    from models.invoice.serie_factura import SerieFactura, SerieFacturaEstado
    from services.acct.seed import seed_default_pgc

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
    terceros: dict[int, dict[str, uuid.UUID]] = {}
    series: dict[int, uuid.UUID] = {}

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(
                    id=1,
                    email="retenciones@admin.test",
                    password_hash=hash_password("pw"),
                    full_name="Admin Retenciones",
                )
            )
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Retenciones Diez SL", 20: "Retenciones Veinte SL"},
            )
            session.add_all(
                [
                    UserCompany(
                        id=1,
                        user_id=1,
                        company_id=10,
                        role=UserRol.ADMIN,
                        is_default=True,
                    ),
                    UserCompany(
                        id=2,
                        user_id=1,
                        company_id=20,
                        role=UserRol.ADMIN,
                    ),
                ]
            )
            await session.flush()
            for empresa_id in (10, 20):
                await seed_default_pgc(session, empresa_id)
                valid = Tercero(
                    empresa_id=empresa_id,
                    nombre=f"Perceptor con NIF {empresa_id}",
                    nif="12345678Z",
                    es_cliente=False,
                    es_proveedor=True,
                )
                missing = Tercero(
                    empresa_id=empresa_id,
                    nombre=f"Perceptor sin NIF {empresa_id}",
                    nif=None,
                    es_cliente=False,
                    es_proveedor=True,
                )
                session.add_all([valid, missing])
                await session.flush()
                session.add_all(
                    [
                        TerceroSubcuenta(
                            empresa_id=empresa_id,
                            tercero_id=valid.id,
                            tipo=TipoSubcuenta.CLIENTE,
                            cuenta_codigo="4300",
                        ),
                        TerceroSubcuenta(
                            empresa_id=empresa_id,
                            tercero_id=valid.id,
                            tipo=TipoSubcuenta.PROVEEDOR,
                            cuenta_codigo="4100",
                        ),
                        TerceroSubcuenta(
                            empresa_id=empresa_id,
                            tercero_id=missing.id,
                            tipo=TipoSubcuenta.CLIENTE,
                            cuenta_codigo="4300",
                        ),
                        TerceroSubcuenta(
                            empresa_id=empresa_id,
                            tercero_id=missing.id,
                            tipo=TipoSubcuenta.PROVEEDOR,
                            cuenta_codigo="4100",
                        ),
                    ]
                )
                serie = SerieFactura(
                    empresa_id=empresa_id,
                    codigo=f"RET{empresa_id}",
                    nombre=f"Serie retenciones {empresa_id}",
                    prefijo=f"RET{empresa_id}",
                    sufijo="",
                    siguiente_numero=0,
                    estado=SerieFacturaEstado.activa,
                )
                session.add(serie)
                await session.flush()
                terceros[empresa_id] = {
                    "con_nif": valid.id,
                    "sin_nif": missing.id,
                }
                series[empresa_id] = serie.id
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(retenciones_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _headers(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_headers,
            terceros=terceros,
            series=series,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            router=retenciones_router,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()



@pytest.fixture
def templates_client():
    """HTTP client de plantillas de asientos (SPEC-018) con empresas A=10 y B=20,
    tres usuarios (ADMIN/ACCOUNTANT/READ_ONLY con vínculo en ambas empresas),
    PGC sembrado y RBAC (trigger) activo. Incluye `templates` + `accounts`."""
    import asyncio
    import types
    from datetime import date as _date

    from sqlalchemy import select as _select

    from api.acct.accounts import router as accounts_router
    from api.templates import router as templates_router
    from models.acct.account_plan import AccountPlan as _AccountPlan
    from models.acct.fiscal_year import FiscalYear
    from services.acct.seed import seed_default_pgc

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
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "A00000001", 20: "B00000002"},
                razones_sociales={10: "Diez SL", 20: "Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    loop = asyncio.new_event_loop()
    try:
        tokens = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(templates_router)
    app.include_router(accounts_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else tokens[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _get(empresa_id: int, ruta: str, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, empresa_id: int = 10, token_key: str = "admin", json=None):
        return client.post(ruta, headers=_hh(token_key, empresa_id), json=json)

    def _patch(ruta: str, empresa_id: int = 10, token_key: str = "admin", json=None):
        return client.patch(ruta, headers=_hh(token_key, empresa_id), json=json)

    def _cuenta(empresa_id: int, code: str) -> int:
        async def _op(session):
            cuenta = await session.scalar(
                _select(_AccountPlan).where(
                    _AccountPlan.tenant_id == empresa_id, _AccountPlan.code == code
                )
            )
            assert cuenta is not None, f"cuenta {code} no sembrada para {empresa_id}"
            return cuenta.id

        return _run(consultar(_op))

    def _marcar_cerrado(empresa_id: int = 10, year: int = 2026):
        async def _op(session):
            existente = await session.scalar(
                _select(FiscalYear).where(
                    FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
                )
            )
            if existente is None:
                session.add(
                    FiscalYear(
                        empresa_id=empresa_id,
                        year=year,
                        date_start=_date(year, 1, 1),
                        date_end=_date(year, 12, 31),
                        is_closed=True,
                    )
                )
            else:
                existente.is_closed = True
            await session.flush()

        return _run(mutar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            tokens=tokens,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            cuenta=_cuenta,
            marcar_cerrado=_marcar_cerrado,
            get=_get,
            post=_post,
            patch=_patch,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def forex_client():
    """HTTP client de multi-divisa (SPEC-016) con 2 empresas (A=10, B=20),
    PGC sembrado y divisa USD registrada en ambas. El catálogo/roles/matriz de
    SPEC-015 se siembran por el trigger de companies; el usuario es ADMIN."""
    import asyncio
    import types
    import uuid as _uuid

    from sqlalchemy import select as _select

    from api.forex.routes import router as forex_router
    from database import get_db
    from models.acct.account_plan import AccountPlan
    from services.acct.seed import seed_default_pgc
    from services.forex.monedas import registrar_divisa

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

    divisas: dict[int, dict[str, _uuid.UUID]] = {}
    cuentas: dict[int, dict[str, int]] = {}

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                cuentas[tenant] = {}
                for codigo in ("4300", "5720"):
                    acc = await session.scalar(
                        _select(AccountPlan).where(
                            AccountPlan.tenant_id == tenant, AccountPlan.code == codigo
                        )
                    )
                    assert acc is not None, f"cuenta {codigo} del PGC no sembrada en {tenant}"
                    cuentas[tenant][codigo] = acc.id
                usd = await registrar_divisa(
                    session, empresa_id=tenant, codigo_iso="USD", activa=True, actor="ana@x.es"
                )
                divisas[tenant] = {"usd": _uuid.UUID(usd["id"])}
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(forex_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _cuentas(empresa_id: int = 10):
        return cuentas[empresa_id]

    def _divisas(empresa_id: int = 10):
        return divisas[empresa_id]

    def _registrar_tipo(empresa_id: int = 10, fecha: str = "2026-10-01", ratio: str = "1.08500000"):
        return client.post(
            "/api/v1/tipos-cambio",
            json={"divisa_id": str(divisas[empresa_id]["usd"]), "fecha": fecha, "ratio": ratio},
            headers=_hh(empresa_id),
        )

    def _asiento_divisa(
        empresa_id: int = 10,
        *,
        fecha: str = "2026-10-01",
        divisa_id=None,
        concepto: str | None = "Venta en USD",
        lineas=None,
        tipo_cambio_id=None,
        ratio_explicito=None,
    ):
        body: dict = {
            "fecha": fecha,
            "divisa_id": str(divisa_id or divisas[empresa_id]["usd"]),
            "concepto": concepto,
            "lineas": lineas
            or [
                {
                    "cuenta_id": cuentas[empresa_id]["4300"],
                    "debe_divisa": "1000.0000",
                    "haber_divisa": "0.0000",
                },
                {
                    "cuenta_id": cuentas[empresa_id]["5720"],
                    "debe_divisa": "0.0000",
                    "haber_divisa": "1000.0000",
                },
            ],
        }
        if tipo_cambio_id is not None:
            body["tipo_cambio_id"] = str(tipo_cambio_id)
        if ratio_explicito is not None:
            body["tipo_ratio_explicito"] = ratio_explicito
        return client.post("/api/v1/asientos-divisa", json=body, headers=_hh(empresa_id))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            cuentas=_cuentas,
            divisas=_divisas,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            registrar_tipo=_registrar_tipo,
            asiento_divisa=_asiento_divisa,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_hh(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_hh(empresa_id), json=json
            ),
            patch=lambda ruta, empresa_id=10, json=None: client.patch(
                ruta, headers=_hh(empresa_id), json=json
            ),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


async def _sembrar_cuenta(
    db: AsyncSession, tenant_id: int, codigo: str, nombre: str, nivel: int, padre: int | None
) -> int:
    cuenta = AccountPlan(
        tenant_id=tenant_id,
        code=codigo,
        name=nombre,
        parent_id=padre,
        level=nivel,
        is_active=True,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta.id


async def _plantar_pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    """Seed minimal PGC chains (Clientes 4/43/430/4300 y Bancos 5/57/572/5720)."""
    cuentas: dict[str, int] = {}
    for (codigo, nombre) in (
        ("4", "Clientes"),
        ("43", "Clientes varios"),
        ("430", "Clientes emisores"),
        ("4300", "Clientes detalle"),
        ("5", "Tesoreria"),
        ("57", "Bancos"),
        ("572", "Bancos c/c"),
        ("5720", "Bancos c/c detalle"),
    ):
        nivel = len(codigo)
        padre = cuentas.get(codigo[:-1]) if len(codigo) > 1 else None
        cuentas[codigo] = await _sembrar_cuenta(db, tenant_id, codigo, nombre, nivel, padre)
    return cuentas


async def _sembrar_contexto(db: AsyncSession) -> dict[str, dict[str, int]]:
    """Seed users/companies/relations + minimal PGC for both test tenants."""
    db.add(
        User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
    )
    await crear_empresas(
        db, 10, 20,
        nifs={10: "A00000001", 20: "B00000002"},
        razones_sociales={10: "Diez SL", 20: "Veinte SL"},
    )
    db.add_all(
        [
            UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
            UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ACCOUNTANT),
        ]
    )
    await db.flush()
    pcg_a = await _plantar_pgc(db, 10)
    pcg_b = await _plantar_pgc(db, 20)
    await db.commit()
    return {"a": pcg_a, "b": pcg_b}


def _motor_setup(engine) -> tuple[str, dict[str, dict[str, int]]]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _config() -> tuple[str, dict[str, dict[str, int]]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            ctx = await _sembrar_contexto(session)
        return emit_token(1), ctx

    return anyio.run(_config)

@pytest.fixture
async def motor_db_session(db_session_factory):
    """Sesión con contexto multi-tenant y PGC plantado (empresas A=10 y B=20)."""
    async with db_session_factory() as session:
        await _sembrar_contexto(session)
        yield session


@pytest.fixture
def journal_client():
    """HTTP client autenticado para /api/v1/journal con 2 empresas (A=10, B=20)
    y PGC mínimos plantados. Devuelve (client, token, cuentas)."""
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
    token, cuentas = _motor_setup(engine)

    app = FastAPI()
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
    anyio.run(_dispose, engine)


@pytest.fixture
def journal_api(journal_client):
    """Helpers HTTP para /api/v1/journal con selección de empresa por header."""
    client, token, cuentas, factory = journal_client
    import types
    import uuid

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _hh(empresa_id: int) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _cuentas(empresa_id: int) -> dict[str, int]:
        return cuentas["a"] if empresa_id == 10 else cuentas["b"]

    def _lineas(empresa_id: int, importe: str = "100.0000") -> list[dict]:
        c = _cuentas(empresa_id)
        return [
            {"account_id": c["4300"], "debit": importe, "credit": "0", "detail": "cliente"},
            {"account_id": c["5720"], "debit": "0", "credit": importe, "detail": "banco"},
        ]

    def crear(empresa_id=10, fecha="2026-01-15", concepto="Venta", lineas=None):
        body = {"fecha": fecha, "concepto": concepto, "lineas": lineas or _lineas(empresa_id)}
        return client.post("/api/v1/journal/entries", json=body, headers=_hh(empresa_id))

    def asentar(entry_id, empresa_id=10):
        return client.post(f"/api/v1/journal/entries/{uuid.UUID(entry_id)}/post", headers=_hh(empresa_id))

    def diario(empresa_id=10, **qp):
        return client.get("/api/v1/journal/entries", params=qp or None, headers=_hh(empresa_id))

    def detalle(entry_id, empresa_id=10):
        return client.get(f"/api/v1/journal/entries/{entry_id}", headers=_hh(empresa_id))

    def anular(entry_id, empresa_id=10, **body):
        return client.post(
            f"/api/v1/journal/entries/{entry_id}/reverse",
            json=body or {},
            headers=_hh(empresa_id),
        )

    return types.SimpleNamespace(
        headers=_hh,
        crear=crear,
        asentar=asentar,
        diario=diario,
        detalle=detalle,
        anular=anular,
        cuentas=cuentas,
        lineas=_lineas,
        consultar=consultar,
        mutar=mutar,
        client=client,
        token=token,
        factory=factory,
    )


@pytest.fixture
def asientos_client():
    """HTTP client para /api/v1/asientos (SPEC-006) con PGC completo
    (16 subcuentas apuntables) en empresas A=10 y B=20."""
    import asyncio

    from api.importexport import router as importexport_router
    from api.journal.asientos import router as asientos_router

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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(importexport_router)
    app.include_router(asientos_router)

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


@pytest.fixture
def efectos_client():
    """HTTP client de medios de pago y efectos (SPEC-021) con 2 empresas
    (A=10, B=20), PGC sembrado, terceros y vencimientos pendientes por empresa,
    usuario ADMIN vinculado a ambas y los routers de tesorería (efectos,
    cobros-medio, vencimientos). RBAC se siembra por el trigger de companies."""
    import asyncio
    import types
    import uuid as _uuid
    from datetime import date as _date
    from decimal import Decimal as _Decimal

    from api.treasury.routes import router as treasury_router
    from models.acct.fiscal_year import FiscalYear
    from models.ar.tercero import Tercero
    from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
    from services.acct.seed import seed_default_pgc

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

    terceros: dict[int, _uuid.UUID] = {}
    vencimientos: dict[int, list[_uuid.UUID]] = {}

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                session.add(
                    FiscalYear(
                        empresa_id=tenant, year=2025,
                        date_start=_date(2025, 1, 1), date_end=_date(2025, 12, 31),
                        is_closed=True,
                    )
                )
                t = Tercero(
                    empresa_id=tenant,
                    nombre=f"Cliente {tenant}",
                    nif=f"B{tenant:08d}",
                    es_cliente=True,
                    es_proveedor=False,
                )
                session.add(t)
                await session.flush()
                terceros[tenant] = t.id
                vencimientos[tenant] = []
                for i in range(2):
                    v = Vencimiento(
                        empresa_id=tenant,
                        tercero_id=t.id,
                        recibo_num=f"V{tenant}-{i}",
                        iban="ES9121000418450200051332",
                        ejercicio=2026,
                        tipo=TipoVencimiento.cobro,
                        fecha_vencimiento=_date(2026, 6, 30),
                        importe=_Decimal("1500.0000"),
                        acumulado=_Decimal("0.0000"),
                        estado=EstadoVencimiento.pendiente,
                    )
                    session.add(v)
                    await session.flush()
                    vencimientos[tenant].append(v.id)
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(treasury_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            terceros=terceros,
            vencimientos=vencimientos,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_hh(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_hh(empresa_id), json=json
            ),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def anticipos_client():
    """HTTP client de anticipos y cesión de cobros (SPEC-022) con 2 empresas
    (A=10, B=20), PGC, terceros (cliente y proveedor), serie + facturas de
    venta/compra, vencimientos pendientes por empresa, usuario ADMIN y los
    routers de tesorería (anticipos, cesiones, vencimientos)."""
    import asyncio
    import types
    import uuid as _uuid
    from datetime import date as _date
    from decimal import Decimal as _Decimal

    from api.treasury.routes import router as treasury_router
    from models.acct.fiscal_year import FiscalYear
    from models.ar.tercero import Tercero
    from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
    from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
    from models.invoice.serie_factura import SerieFactura, SerieFacturaEstado
    from services.acct.seed import seed_default_pgc

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

    terceros: dict[int, _uuid.UUID] = {}
    proveedores: dict[int, _uuid.UUID] = {}
    facturas: dict[int, dict[str, _uuid.UUID]] = {}
    vencimientos: dict[int, list[_uuid.UUID]] = {}

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                session.add(
                    FiscalYear(
                        empresa_id=tenant, year=2025,
                        date_start=_date(2025, 1, 1), date_end=_date(2025, 12, 31),
                        is_closed=True,
                    )
                )
                cliente = Tercero(
                    empresa_id=tenant, nombre=f"Cliente {tenant}",
                    nif=f"B{tenant:08d}", es_cliente=True, es_proveedor=False,
                )
                proveedor = Tercero(
                    empresa_id=tenant, nombre=f"Proveedor {tenant}",
                    nif=f"B{tenant:09d}", es_cliente=False, es_proveedor=True,
                )
                session.add_all([cliente, proveedor])
                await session.flush()
                terceros[tenant] = cliente.id
                proveedores[tenant] = proveedor.id
                serie = SerieFactura(
                    empresa_id=tenant, codigo="SERIE", nombre="Serie", prefijo="F",
                    siguiente_numero=3, estado=SerieFacturaEstado.activa,
                )
                session.add(serie)
                await session.flush()
                venta = Factura(
                    empresa_id=tenant, serie_id=serie.id, numero=1, ejercicio=2026,
                    fecha=_date(2026, 2, 1), tipo=FacturaTipo.VENTA, tercero_id=cliente.id,
                    importe_total=_Decimal("2500.0000"), estado=FacturaEstado.emitida,
                )
                compra = Factura(
                    empresa_id=tenant, serie_id=serie.id, numero=2, ejercicio=2026,
                    fecha=_date(2026, 2, 2), tipo=FacturaTipo.COMPRA, tercero_id=proveedor.id,
                    importe_total=_Decimal("2000.0000"), estado=FacturaEstado.emitida,
                )
                session.add_all([venta, compra])
                await session.flush()
                facturas[tenant] = {"venta": venta.id, "compra": compra.id}
                vencimientos[tenant] = []
                for i in range(2):
                    v = Vencimiento(
                        empresa_id=tenant,
                        tercero_id=cliente.id,
                        recibo_num=f"V{tenant}-{i}",
                        iban="ES9121000418450200051332",
                        ejercicio=2026,
                        tipo=TipoVencimiento.cobro,
                        fecha_vencimiento=_date(2026, 6, 30),
                        importe=_Decimal("1500.0000"),
                        acumulado=_Decimal("0.0000"),
                        estado=EstadoVencimiento.pendiente,
                    )
                    session.add(v)
                    await session.flush()
                    vencimientos[tenant].append(v.id)
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(treasury_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            terceros=terceros,
            proveedores=proveedores,
            facturas=facturas,
            vencimientos=vencimientos,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_hh(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_hh(empresa_id), json=json
            ),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def facturacion_client():
    """HTTP client de facturación (SPEC-007) con PGC + cuentas fiscales
    (472/475/477 y subcuentas), terceros con subcuentas 430/410 y una serie
    activa por empresa (A=10, B=20)."""
    import types
    import uuid as _uuid

    from api.invoicing.facturas import router as facturas_router
    from api.invoicing.series import router as series_router
    from api.journal.asientos import router as asientos_router
    from models.acct.account_plan import AccountPlan
    from models.ar.tercero import Tercero
    from models.ar.tercero_subcuenta import TerceroSubcuenta, TipoSubcuenta
    from models.invoice.serie_factura import SerieFactura, SerieFacturaEstado
    from services.acct.seed import seed_default_pgc

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

    async def _plantar_fiscales(session, tenant_id: int) -> None:
        from sqlalchemy import select as _select

        padre = await session.scalar(
            _select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id, AccountPlan.code == "47"
            )
        )
        assert padre is not None
        fiscales = {
            "472": [("4720", "IVA soportado"), ("4722", "Recargo soportado")],
            "475": [("4751", "IRPF retenido")],
            "477": [("4770", "IVA repercutido"), ("4772", "Recargo repercutido")],
        }
        for code, subs in fiscales.items():
            n3 = await session.scalar(
                _select(AccountPlan).where(
                    AccountPlan.tenant_id == tenant_id, AccountPlan.code == code
                )
            )
            if n3 is None:
                n3 = AccountPlan(
                    tenant_id=tenant_id,
                    code=code,
                    level=3,
                    name=code,
                    parent_id=padre.id,
                    is_selectable=False,
                )
                session.add(n3)
                await session.flush()
            for sub, subname in subs:
                existente = await session.scalar(
                    _select(AccountPlan).where(
                        AccountPlan.tenant_id == tenant_id, AccountPlan.code == sub
                    )
                )
                if existente is None:
                    session.add(
                        AccountPlan(
                            tenant_id=tenant_id,
                            code=sub,
                            level=4,
                            name=subname,
                            parent_id=n3.id,
                            is_selectable=True,
                        )
                    )
                    await session.flush()

    terceros: dict[int, _uuid.UUID] = {}
    series: dict[int, _uuid.UUID] = {}

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                await _plantar_fiscales(session, tenant)
                t = Tercero(
                    empresa_id=tenant,
                    nombre=f"Tercero {tenant}",
                    nif=f"B{tenant:08d}",
                    es_cliente=True,
                    es_proveedor=True,
                )
                session.add(t)
                await session.flush()
                session.add_all(
                    [
                        TerceroSubcuenta(
                            empresa_id=tenant,
                            tercero_id=t.id,
                            tipo=TipoSubcuenta.CLIENTE,
                            cuenta_codigo="4300",
                        ),
                        TerceroSubcuenta(
                            empresa_id=tenant,
                            tercero_id=t.id,
                            tipo=TipoSubcuenta.PROVEEDOR,
                            cuenta_codigo="4100",
                        ),
                    ]
                )
                s = SerieFactura(
                    empresa_id=tenant,
                    codigo=f"S{tenant}",
                    nombre=f"Serie {tenant}",
                    prefijo=f"S{tenant}",
                    sufijo="",
                    siguiente_numero=0,
                    estado=SerieFacturaEstado.activa,
                )
                session.add(s)
                await session.flush()
                terceros[tenant] = t.id
                series[tenant] = s.id
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(facturas_router)
    app.include_router(series_router)
    app.include_router(asientos_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _linea(
        descripcion: str = "Producto",
        cantidad: str = "1",
        precio: str = "100.0000",
        tipo_iva: str = "21",
        tipo_recargo: str = "0",
        tipo_irpf: str = "0",
        base_irpf: str = "0",
        descuento: str = "0",
    ) -> dict:
        return {
            "descripcion": descripcion,
            "cantidad": cantidad,
            "precio_unitario": precio,
            "porcentaje_descuento": descuento,
            "tipo_iva": tipo_iva,
            "tipo_recargo": tipo_recargo,
            "tipo_irpf": tipo_irpf,
            "base_irpf": base_irpf,
        }

    def _crear(
        empresa_id: int = 10,
        *,
        tipo: str = "VENTA",
        fecha: str = "2026-03-01",
        ejercicio: int = 2026,
        serie_id=None,
        tercero_id=None,
        lineas=None,
        regimen_caja: bool = False,
        concepto: str = "Factura test",
    ):
        body = {
            "serie_id": str(serie_id or series[empresa_id]),
            "ejercicio": ejercicio,
            "fecha": fecha,
            "tipo": tipo,
            "tercero_id": str(tercero_id or terceros[empresa_id]),
            "concepto_global": concepto,
            "regimen_caja": regimen_caja,
            "lineas": lineas or [_linea()],
        }
        return client.post(
            "/api/v1/facturacion/facturas", json=body, headers=_hh(empresa_id)
        )

    def _emitir(factura_id, empresa_id: int = 10):
        return client.post(
            f"/api/v1/facturacion/facturas/{factura_id}/emitir", headers=_hh(empresa_id)
        )

    def _rectificar(factura_id, empresa_id: int = 10, *, motivo="Error", serie_id=None, lineas=None):
        body: dict = {
            "serie_id": str(serie_id or series[empresa_id]),
            "motivo": motivo,
        }
        if lineas is not None:
            body["lineas"] = lineas
        return client.post(
            f"/api/v1/facturacion/facturas/{factura_id}/rectificar",
            json=body,
            headers=_hh(empresa_id),
        )

    def _anular(factura_id, empresa_id: int = 10):
        return client.post(
            f"/api/v1/facturacion/facturas/{factura_id}/anular", headers=_hh(empresa_id)
        )

    def _listar(empresa_id: int = 10, **qp):
        return client.get(
            "/api/v1/facturacion/facturas", params=qp or None, headers=_hh(empresa_id)
        )

    def _detalle(factura_id, empresa_id: int = 10):
        return client.get(
            f"/api/v1/facturacion/facturas/{factura_id}", headers=_hh(empresa_id)
        )

    def _eliminar(factura_id, empresa_id: int = 10):
        return client.delete(
            f"/api/v1/facturacion/facturas/{factura_id}", headers=_hh(empresa_id)
        )

    def _asiento(entry_id, empresa_id: int = 10):
        return client.get(f"/api/v1/asientos/{entry_id}", headers=_hh(empresa_id))

    def _crear_serie(empresa_id: int = 10, codigo: str = "R", prefijo: str = "R", nombre: str = "Rect"):
        return client.post(
            "/api/v1/facturacion/series",
            json={"codigo": codigo, "nombre": nombre, "prefijo": prefijo},
            headers=_hh(empresa_id),
        )

    def _estado_serie(serie_id, activa: bool, empresa_id: int = 10):
        return client.patch(
            f"/api/v1/facturacion/series/{serie_id}/estado",
            json={"activa": activa},
            headers=_hh(empresa_id),
        )

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            terceros=terceros,
            series=series,
            linea=_linea,
            crear=_crear,
            emitir=_emitir,
            rectificar=_rectificar,
            anular=_anular,
            listar=_listar,
            detalle=_detalle,
            eliminar=_eliminar,
            asiento=_asiento,
            crear_serie=_crear_serie,
            estado_serie=_estado_serie,
            consultar=consultar,
            mutar=mutar,
            run=_run,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def costcenters_client():
    """HTTP client de centros de coste (SPEC-017) con PGC en empresas A=10 y B=20,
    un usuario ADMIN y los routers `costcenters` + `asientos` (motor multilínea)."""
    import asyncio

    from api.costcenters.routes import router as costcenters_router
    from api.journal.asientos import router as asientos_router

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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(costcenters_router)
    app.include_router(asientos_router)

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


@pytest.fixture
def cuentas_client():
    """HTTP client de cuentas anuales (SPEC-010) con PGC y diario sembrados en
    empresas A=10 y B=20 (importes distintos para probar aislamiento)."""
    import asyncio
    import types
    from datetime import date as _date

    from api.cuentas_anuales.routes import router as cuentas_router
    from models.acct.account_plan import AccountPlan as _AccountPlan
    from models.acct.fiscal_year import FiscalYear
    from services.closing.close_year import cerrar_ejercicio
    from services.journal.motor import crear_asiento_multilinea

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

    async def _asiento(session, empresa_id, lineas, fecha, concepto="Asiento test"):
        return await crear_asiento_multilinea(
            session,
            empresa_id=empresa_id,
            fecha=fecha,
            concepto=concepto,
            lineas=lineas,
        )

    def _linea(cuenta, importe, lado):
        if lado == "D":
            return {"cuenta": cuenta, "debe": importe, "haber": "0", "detalle": cuenta}
        return {"cuenta": cuenta, "debe": "0", "haber": importe, "detalle": cuenta}

    async def _sembrar_diario(session) -> None:
        fecha = _date(2026, 3, 1)
        from sqlalchemy import select as _select

        for tenant in (10, 20):
            padre = await session.scalar(
                _select(_AccountPlan).where(
                    _AccountPlan.tenant_id == tenant, _AccountPlan.code == "12"
                )
            )
            session.add(
                _AccountPlan(
                    tenant_id=tenant,
                    code="129",
                    name="Resultado del ejercicio",
                    level=3,
                    parent_id=padre.id,
                    is_active=True,
                )
            )
            await session.flush()
        await _asiento(
            session, 10,
            [_linea("5720", "10000.0000", "D"), _linea("1110", "10000.0000", "H")],
            fecha, "Aportacion socios",
        )
        await _asiento(
            session, 10,
            [_linea("2100", "3000.0000", "D"), _linea("5720", "3000.0000", "H")],
            fecha, "Compra inmovilizado",
        )
        await _asiento(
            session, 10,
            [_linea("4300", "5000.0000", "D"), _linea("7000", "5000.0000", "H")],
            fecha, "Venta",
        )
        await _asiento(
            session, 10,
            [_linea("6400", "2000.0000", "D"), _linea("5720", "2000.0000", "H")],
            fecha, "Sueldos",
        )
        await _asiento(
            session, 20,
            [_linea("5720", "2000.0000", "D"), _linea("1110", "2000.0000", "H")],
            fecha, "Aportacion socios B",
        )
        await _asiento(
            session, 20,
            [_linea("4300", "800.0000", "D"), _linea("7000", "800.0000", "H")],
            fecha, "Venta B",
        )

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            await _sembrar_diario(session)
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(cuentas_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _cerrar(empresa_id: int = 10, year: int = 2026):
        async def _op(session):
            session.add(
                FiscalYear(
                    empresa_id=empresa_id,
                    year=year,
                    date_start=_date(year, 1, 1),
                    date_end=_date(year, 12, 31),
                    is_closed=False,
                )
            )
            await session.flush()
            return await cerrar_ejercicio(
                session, empresa_id=empresa_id, year=year, actor="ana@x.es"
            )

        return _run(mutar(_op))

    def _asiento_ep(empresa_id, lineas, fecha, concepto="Asiento test"):
        fecha_date = _date.fromisoformat(fecha) if isinstance(fecha, str) else fecha
        return _run(
            mutar(lambda s: _asiento(s, empresa_id, lineas, fecha_date, concepto))
        )

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            cerrar=_cerrar,
            asiento=_asiento_ep,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_hh(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_hh(empresa_id), json=json
            ),
            patch=lambda ruta, empresa_id=10, json=None: client.patch(
                ruta, headers=_hh(empresa_id), json=json
            ),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def fiscal_client():
    """HTTP client fiscal (SPEC-012) con PGC + cuentas de IVA, terceros (ES e
    intracomunitario) y facturas emitidas/recibidas con asiento en A=10 y B=20."""
    import asyncio
    import types as _types
    import uuid as _uuid
    from datetime import date as _date

    from api.fiscal.routes import router as fiscal_router
    from models.acct.account_plan import AccountPlan
    from models.ar.tercero import Tercero
    from models.ar.tercero_subcuenta import TerceroSubcuenta, TipoSubcuenta
    from models.invoice.serie_factura import SerieFactura, SerieFacturaEstado
    from services.acct.seed import seed_default_pgc
    from services.invoicing.emision import crear_factura_borrador, emitir_factura

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

    async def _plantar_fiscales(session, tenant_id: int) -> None:
        from sqlalchemy import select as _select

        padre = await session.scalar(
            _select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id, AccountPlan.code == "47"
            )
        )
        fiscales = {
            "472": [("4720", "IVA soportado"), ("4722", "Recargo soportado")],
            "475": [("4751", "IRPF retenido")],
            "477": [("4770", "IVA repercutido"), ("4772", "Recargo repercutido")],
        }
        for code, subs in fiscales.items():
            n3 = await session.scalar(
                _select(AccountPlan).where(
                    AccountPlan.tenant_id == tenant_id, AccountPlan.code == code
                )
            )
            if n3 is None:
                n3 = AccountPlan(
                    tenant_id=tenant_id,
                    code=code,
                    level=3,
                    name=code,
                    parent_id=padre.id if padre else None,
                    is_selectable=False,
                )
                session.add(n3)
                await session.flush()
            for sub, subname in subs:
                existente = await session.scalar(
                    _select(AccountPlan).where(
                        AccountPlan.tenant_id == tenant_id, AccountPlan.code == sub
                    )
                )
                if existente is None:
                    session.add(
                        AccountPlan(
                            tenant_id=tenant_id,
                            code=sub,
                            level=4,
                            name=subname,
                            parent_id=n3.id,
                            is_selectable=True,
                        )
                    )
                    await session.flush()

    async def _tercero(session, tenant_id: int, nombre: str, nif: str, iban: str):
        t = Tercero(
            empresa_id=tenant_id,
            nombre=nombre,
            nif=nif,
            iban=iban,
            es_cliente=True,
            es_proveedor=True,
        )
        session.add(t)
        await session.flush()
        session.add_all(
            [
                TerceroSubcuenta(
                    empresa_id=tenant_id,
                    tercero_id=t.id,
                    tipo=TipoSubcuenta.CLIENTE,
                    cuenta_codigo="4300",
                ),
                TerceroSubcuenta(
                    empresa_id=tenant_id,
                    tercero_id=t.id,
                    tipo=TipoSubcuenta.PROVEEDOR,
                    cuenta_codigo="4100",
                ),
            ]
        )
        await session.flush()
        return t.id

    async def _facturar(
        session,
        *,
        empresa_id: int,
        serie_id: _uuid.UUID,
        tercero_id: _uuid.UUID,
        tipo: str,
        base: str,
        iva: str = "21",
        recargo: str = "0",
        fecha: _date | None = None,
        regimen_caja: bool = False,
    ) -> _uuid.UUID:
        fecha = fecha or _date(2026, 1, 15)
        lineas = [
            {
                "descripcion": "operacion",
                "cantidad": "1",
                "precio_unitario": base,
                "porcentaje_descuento": "0",
                "tipo_iva": iva,
                "tipo_recargo": recargo,
                "tipo_irpf": "0",
                "base_irpf": "0",
            }
        ]
        factura = await crear_factura_borrador(
            session,
            empresa_id=empresa_id,
            serie_id=serie_id,
            ejercicio=fecha.year,
            fecha=fecha,
            tipo=tipo,
            tercero_id=tercero_id,
            concepto_global="operacion",
            lineas=lineas,
            regimen_caja=regimen_caja,
        )
        await emitir_factura(session, empresa_id=empresa_id, factura_id=factura.id)
        return factura.id

    terceros: dict[int, dict[str, _uuid.UUID]] = {}
    series: dict[int, _uuid.UUID] = {}
    facturas: dict[int, dict[str, _uuid.UUID]] = {}

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "B00000010", 20: "B00000020"},
                razones_sociales={10: "Diez SL", 20: "Veinte SL"},
            )
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                ]
            )
            await session.flush()
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                await _plantar_fiscales(session, tenant)
                cliente = await _tercero(
                    session, tenant, f"Cliente {tenant}", f"B{tenant:08d}", f"ES91{tenant:018d}"
                )
                proveedor = await _tercero(
                    session, tenant, f"Proveedor {tenant}", f"A{tenant:08d}", f"ES92{tenant:018d}"
                )
                intra = await _tercero(
                    session, tenant, f"Intra {tenant}", "DE123456789", "DE89370400440532013000"
                )
                s = SerieFactura(
                    empresa_id=tenant,
                    codigo=f"S{tenant}",
                    nombre=f"Serie {tenant}",
                    prefijo=f"S{tenant}",
                    sufijo="",
                    siguiente_numero=0,
                    estado=SerieFacturaEstado.activa,
                )
                session.add(s)
                await session.flush()
                base_venta = "10000.0000" if tenant == 10 else "2000.0000"
                base_compra = "5000.0000" if tenant == 10 else "1000.0000"
                venta = await _facturar(
                    session, empresa_id=tenant, serie_id=s.id, tercero_id=cliente,
                    tipo="VENTA", base=base_venta,
                )
                compra = await _facturar(
                    session, empresa_id=tenant, serie_id=s.id, tercero_id=proveedor,
                    tipo="COMPRA", base=base_compra,
                )
                terceros[tenant] = {"cliente": cliente, "proveedor": proveedor, "intra": intra}
                series[tenant] = s.id
                facturas[tenant] = {"venta": venta, "compra": compra}
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
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

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _facturar_ep(
        empresa_id=10,
        tipo="VENTA",
        base="1000.0000",
        tercero_key="cliente",
        iva="21",
        recargo="0",
        fecha="2026-01-15",
        regimen_caja=False,
    ):
        fecha_date = _date.fromisoformat(fecha)

        def _op(session):
            return _facturar(
                session,
                empresa_id=empresa_id,
                serie_id=series[empresa_id],
                tercero_id=terceros[empresa_id][tercero_key],
                tipo=tipo,
                base=base,
                iva=iva,
                recargo=recargo,
                fecha=fecha_date,
                regimen_caja=regimen_caja,
            )

        return _run(mutar(_op))

    with TestClient(app) as client:
        yield _types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            facturar=_facturar_ep,
            terceros=terceros,
            series=series,
            facturas=facturas,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_hh(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_hh(empresa_id), json=json
            ),
            patch=lambda ruta, empresa_id=10, json=None: client.patch(
                ruta, headers=_hh(empresa_id), json=json
            ),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


async def _dispose(engine) -> None:
    await engine.dispose()


_PADRES_INMOVILIZADO = {
    "21": "2",
    "28": "2",
    "67": "6",
    "77": "7",
    "218": "21",
    "281": "28",
    "671": "67",
    "771": "77",
    "2180": "218",
    "2818": "281",
    "6710": "671",
    "7710": "771",
}


async def _plantar_inmovilizado(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    """Plantar la cadena 21x + 687/281 + 671/771 del inmovilizado (SPEC-014).

    El PGC base (SPEC-001) ya trae 2100/2810/6810/5720 pero NO 6710/7710 ni las
    variantes 218/2180/2818; las crea bajo su padre si el seed no las incluye
    (respetando ``level == len(code)``).
    """
    from sqlalchemy import select as _select

    ids: dict[str, int] = {}
    for codigo, nombre in (
        ("21", "Inmovilizado material"),
        ("28", "Amortización acumulada"),
        ("67", "Pérdidas procedentes de inmovilizado"),
        ("77", "Beneficios procedentes de inmovilizado"),
        ("218", "Elementos de transporte"),
        ("281", "Amortización acumulada del inmovilizado material"),
        ("671", "Pérdidas procedentes del inmovilizado"),
        ("771", "Beneficios procedentes del inmovilizado"),
        ("2180", "Elementos de transporte detalle"),
        ("2818", "AAI elementos de transporte"),
        ("6710", "Pérdidas inmovilizado detalle"),
        ("7710", "Beneficios inmovilizado detalle"),
    ):
        if codigo in ids:
            continue
        existente = await db.scalar(
            _select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id, AccountPlan.code == codigo
            )
        )
        if existente is not None:
            ids[codigo] = existente.id
            continue
        nivel = len(codigo)
        padre = ids.get(_PADRES_INMOVILIZADO[codigo])
        if padre is None and nivel > 1:
            padre = await db.scalar(
                _select(AccountPlan).where(
                    AccountPlan.tenant_id == tenant_id,
                    AccountPlan.code == _PADRES_INMOVILIZADO[codigo],
                )
            )
            if padre is not None:
                padre = padre.id
        cuenta = AccountPlan(
            tenant_id=tenant_id,
            code=codigo,
            name=nombre,
            parent_id=padre,
            level=nivel,
            is_active=True,
            is_selectable=(nivel == 4),
        )
        db.add(cuenta)
        await db.flush()
        ids[codigo] = cuenta.id
    return ids


@pytest.fixture
def inmovilizado_client():
    """HTTP client de inmovilizado (SPEC-014) con PGC + cuentas específicas
    (218/2180, 2818, 671/6710, 771/7710) en empresas A=10 y B=20."""
    import asyncio
    import types
    from datetime import date as _date

    from api.inmovilizado.routes import router as inmovilizado_router
    from models.acct.fiscal_year import FiscalYear
    from services.acct.seed import seed_default_pgc

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

    async def _setup() -> tuple[str, dict[str, dict[str, int]]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        cuentas_empresa: dict[str, dict[str, int]] = {}
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                cuentas_empresa[str(tenant)] = await _plantar_inmovilizado(session, tenant)
            await session.commit()
        return emit_token(1), cuentas_empresa

    loop = asyncio.new_event_loop()
    try:
        token, cuentas_empresa = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(inmovilizado_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _cuentas(empresa_id: int = 10):
        return cuentas_empresa[str(empresa_id)]

    def _crear(
        empresa_id: int = 10,
        *,
        numero_activo: str = "EQ-001",
        cuenta_id=None,
        descripcion: str = "Equipo informático",
        fecha_alta: str = "2026-01-01",
        coste_amortizable: str = "15000.0000",
        vida_util: int = 60,
        metodo: str = "lineal",
        porcentaje_regresivo: str | None = None,
        cuenta_gasto_id=None,
        cuenta_acumulada_id=None,
    ):
        body = {
            "numero_activo": numero_activo,
            "cuenta_id": cuenta_id if cuenta_id is not None else _cuentas(empresa_id).get("2100") or _cuentas(empresa_id)["2180"],
            "descripcion": descripcion,
            "fecha_alta": fecha_alta,
            "coste_amortizable": coste_amortizable,
            "vida_util": vida_util,
            "metodo": metodo,
        }
        if porcentaje_regresivo is not None:
            body["porcentaje_regresivo"] = porcentaje_regresivo
        if cuenta_gasto_id is not None:
            body["cuenta_gasto_id"] = cuenta_gasto_id
        if cuenta_acumulada_id is not None:
            body["cuenta_acumulada_id"] = cuenta_acumulada_id
        return client.post("/api/v1/activos", json=body, headers=_hh(empresa_id))

    def _marcar_cerrado(empresa_id: int = 10, year: int = 2026):
        async def _op(session):
            session.add(
                FiscalYear(
                    empresa_id=empresa_id,
                    year=year,
                    date_start=_date(year, 1, 1),
                    date_end=_date(year, 12, 31),
                    is_closed=True,
                )
            )
            await session.flush()

        return _run(mutar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            cuentas=_cuentas,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            crear=_crear,
            marcar_cerrado=_marcar_cerrado,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_hh(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_hh(empresa_id), json=json
            ),
            patch=lambda ruta, empresa_id=10, json=None: client.patch(
                ruta, headers=_hh(empresa_id), json=json
            ),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def rbac_client():
    """HTTP client de la matriz de permisos (SPEC-015) con empresas A=10 y B=20,
    tres usuarios (ADMIN/ACCOUNTANT/READ_ONLY con vínculo en ambas empresas) y
    PGC sembrado; incluye los routers `rbac`, `accounts` y `journal`."""
    import asyncio
    import types

    from api.acct.accounts import router as accounts_router
    from api.journal.journal import router as journal_router
    from api.rbac import router as rbac_router
    from services.acct.seed import seed_default_pgc

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
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "A00000001", 20: "B00000002"},
                razones_sociales={10: "Diez SL", 20: "Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            for tenant in (10, 20):
                # El trigger trg_companies_rbac_seed ya crea roles + matriz.
                await seed_default_pgc(session, tenant)
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    loop = asyncio.new_event_loop()
    try:
        tokens = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(rbac_router)
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

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else tokens[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    def _get(empresa_id: int, ruta: str, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, empresa_id: int = 10, token_key: str = "admin", json=None):
        return client.post(ruta, headers=_hh(token_key, empresa_id), json=json)

    def _delete(ruta: str, empresa_id: int = 10, token_key: str = "admin"):
        return client.delete(ruta, headers=_hh(token_key, empresa_id))

    def _resolver_rol(empresa_id: int, nombre: str):
        from sqlalchemy import select as _select

        from models.rbac.rol import Rol

        async def _op(session):
            rol = await session.scalar(
                _select(Rol).where(Rol.empresa_id == empresa_id, Rol.nombre == nombre)
            )
            assert rol is not None
            return str(rol.id)

        return _run(consultar(_op))

    def _resolver_permiso(modulo: str, operacion: str):
        from sqlalchemy import select as _select

        from models.rbac.permiso_operacion import OperacionPermiso, PermisoOperacion

        async def _op(session):
            permiso = await session.scalar(
                _select(PermisoOperacion).where(
                    PermisoOperacion.modulo == modulo,
                    PermisoOperacion.operacion == OperacionPermiso(operacion),
                )
            )
            assert permiso is not None
            return str(permiso.id)

        return _run(consultar(_op))

    def _conceder(empresa_id: int, rol_nombre: str, modulo: str, operacion: str, token_key: str = "admin"):
        return _post(
            "/api/v1/permisos/matriz",
            empresa_id,
            token_key,
            json={"rol_id": _resolver_rol(empresa_id, rol_nombre), "modulo": modulo, "operacion": operacion},
        )

    def _matriz_id(empresa_id: int, rol_nombre: str, modulo: str, operacion: str):
        from sqlalchemy import select as _select

        from models.rbac.matriz_permiso import MatrizPermiso
        from models.rbac.permiso_operacion import OperacionPermiso, PermisoOperacion
        from models.rbac.rol import Rol

        async def _op(session):
            fila = await session.scalar(
                _select(MatrizPermiso.id)
                .join(Rol, (Rol.empresa_id == MatrizPermiso.empresa_id) & (Rol.id == MatrizPermiso.rol_id))
                .join(PermisoOperacion, PermisoOperacion.id == MatrizPermiso.permiso_id)
                .where(
                    MatrizPermiso.empresa_id == empresa_id,
                    Rol.nombre == rol_nombre,
                    PermisoOperacion.modulo == modulo,
                    PermisoOperacion.operacion == OperacionPermiso(operacion),
                )
            )
            return None if fila is None else str(fila)

        return _run(consultar(_op))

    def _conteo_eventos(empresa_id: int, resultado: str | None = None):
        from sqlalchemy import func as _func
        from sqlalchemy import select as _select

        from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso

        async def _op(session):
            condiciones = [EventoAuditoriaAcceso.empresa_id == empresa_id]
            if resultado is not None:
                condiciones.append(EventoAuditoriaAcceso.resultado == resultado)
            return await session.scalar(
                _select(_func.count()).select_from(EventoAuditoriaAcceso).where(*condiciones)
            )

        return _run(consultar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=tokens,
            tokens=tokens,
            factory=factory,
            headers=_hh,
            consultar=consultar,
            mutar=mutar,
            run=_run,
            get=_get,
            post=_post,
            delete=_delete,
            resolver_rol=_resolver_rol,
            resolver_permiso=_resolver_permiso,
            conceder=_conceder,
            matriz_id=_matriz_id,
            conteo_eventos=_conteo_eventos,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def ngo_client():
    """HTTP + DB client de Gestión ONG (SPEC-019) con PGC en A=10 y B=20, subcuenta
    5700 apuntable, un diario de 2025 (cerrable vía `cerrar`) y un ejercicio 2026
    abierto. Routers `ngo` + `asientos` (motor multilínea)."""
    import asyncio
    import types
    from datetime import date as _date

    from sqlalchemy import select

    from api.journal.asientos import router as asientos_router
    from api.ngo.routes import router as ngo_router
    from models.acct.account_plan import AccountPlan
    from models.acct.fiscal_year import FiscalYear
    from services.journal.motor import crear_asiento_multilinea

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

    async def _plantar_5700(session, tenant_id: int) -> None:
        padre = await session.scalar(
            select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id, AccountPlan.code == "570"
            )
        )
        if padre is None:
            return False
        ya = await session.scalar(
            select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id, AccountPlan.code == "5700"
            )
        )
        if ya is not None:
            return True
        session.add(
            AccountPlan(
                tenant_id=tenant_id,
                code="5700",
                name="Caja euro",
                level=4,
                parent_id=padre.id,
                is_selectable=True,
            )
        )
        await session.flush()
        return True

    def _linea(cuenta, importe, lado):
        if lado == "D":
            return {"cuenta": cuenta, "debe": importe, "haber": "0", "detalle": cuenta}
        return {"cuenta": cuenta, "debe": "0", "haber": importe, "detalle": cuenta}

    async def _asiento(session, empresa_id, lineas, fecha, concepto="Asiento test"):
        return await crear_asiento_multilinea(
            session,
            empresa_id=empresa_id,
            fecha=fecha,
            concepto=concepto,
            lineas=lineas,
        )

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await sembrar_empresas_pgc(
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
            await _plantar_5700(session, 10)
            await _plantar_5700(session, 20)
            # Diario de 2025 (ejercicio abierto hasta `cerrar`)
            await _asiento(
                session, 10,
                [_linea("5720", "10000.0000", "D"), _linea("1110", "10000.0000", "H")],
                _date(2025, 3, 1), "Aportacion socios",
            )
            await _asiento(
                session, 10,
                [_linea("6400", "2000.0000", "D"), _linea("5720", "2000.0000", "H")],
                _date(2025, 4, 15), "Sueldos",
            )
            await _asiento(
                session, 20,
                [_linea("5720", "5000.0000", "D"), _linea("1110", "5000.0000", "H")],
                _date(2025, 2, 10), "Aportacion B",
            )
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(ngo_router)
    app.include_router(asientos_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _asiento_ep(empresa_id, lineas, fecha, concepto="Asiento test"):
        fecha_date = _date.fromisoformat(fecha) if isinstance(fecha, str) else fecha
        return _run(mutar(lambda s: _asiento(s, empresa_id, lineas, fecha_date, concepto)))

    def _subcuenta_570(empresa_id: int = 10):
        async def _op(session):
            return await session.scalar(
                select(AccountPlan.id).where(
                    AccountPlan.tenant_id == empresa_id, AccountPlan.code == "5700"
                )
            )

        return _run(consultar(_op))

    def _cerrar(empresa_id: int = 10, year: int = 2025):
        async def _op(session):
            fy = await session.scalar(
                select(FiscalYear).where(
                    FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
                )
            )
            if fy is None:
                fy = FiscalYear(
                    empresa_id=empresa_id,
                    year=year,
                    date_start=_date(year, 1, 1),
                    date_end=_date(year, 12, 31),
                )
                session.add(fy)
                await session.flush()
            fy.is_closed = True
            await session.flush()
            return year

        return _run(mutar(_op))

    def _crear_subvencion(empresa_id=10, importe="10000.0000", ejercicio=2025, **kw):
        from decimal import Decimal

        from services.ngo.subvenciones import crear_subvencion

        return _run(
            mutar(
                lambda s: crear_subvencion(
                    s,
                    empresa_id=empresa_id,
                    entidad_concedente=kw.get("entidad", "Ayto"),
                    programa=kw.get("programa", "Voluntariado"),
                    referencia=kw.get("referencia"),
                    importe_concedido=Decimal(str(importe)),
                    ejercicio=ejercicio,
                    observaciones=kw.get("observaciones"),
                    partidas=kw.get("partidas"),
                )
            )
        )

    def _legalizar_directa(empresa_id: int = 10, ejercicio: int = 2025):
        """Legalización valida (para probar FR-007) sin pasar por la emisión."""

        async def _op(session):
            from models.ngo.libros import Legalizacion

            session.add(
                Legalizacion(
                    empresa_id=empresa_id,
                    ejercicio=ejercicio,
                    rango_asientos_desde=1,
                    rango_asientos_hasta=1,
                    total_asientos=1,
                    huella="0" * 64,
                    fecha_emision=_date(2025, 12, 31),
                )
            )
            await session.flush()

        return _run(mutar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            asiento=_asiento_ep,
            subcuenta_570=_subcuenta_570,
            cerrar=_cerrar,
            crear_subvencion=_crear_subvencion,
            legalizar_directa=_legalizar_directa,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_hh(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_hh(empresa_id), json=json
            ),
            patch=lambda ruta, empresa_id=10, json=None: client.patch(
                ruta, headers=_hh(empresa_id), json=json
            ),
            delete=lambda ruta, empresa_id=10: client.delete(ruta, headers=_hh(empresa_id)),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def is_client():
    import types
    import uuid
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import select as _select

    from api.fiscal.routes import router as fiscal_router
    from models.acct.account_plan import AccountPlan
    from models.acct.fiscal_year import FiscalYear
    from models.acct.journal import (
        JournalEntry,
        JournalEntryEstado,
        JournalEntryLine,
        JournalEntryTipo,
    )
    from models.acct.journal_sequence import SecuenciaAsiento
    from models.fiscal.configuracion_fiscal import ConfiguracionFiscal
    from services.acct.seed import seed_default_pgc

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

    async def _setup() -> str:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add(
                User(
                    id=1,
                    email="is@admin.test",
                    password_hash=hash_password("pw"),
                    full_name="Admin IS",
                )
            )
            for empresa_id, nif, nombre in (
                (10, "A00000010", "Sociedad Diez SL"),
                (20, "B00000020", "Sociedad Veinte SL"),
            ):
                session.add(
                    Company(company_id=empresa_id, nif=nif, razon_social=nombre)
                )
            await session.flush()
            session.add_all(
                [
                    UserCompany(
                        id=1,
                        user_id=1,
                        company_id=10,
                        role=UserRol.ADMIN,
                        is_default=True,
                    ),
                    UserCompany(
                        id=2,
                        user_id=1,
                        company_id=20,
                        role=UserRol.ADMIN,
                    ),
                ]
            )
            for empresa_id in (10, 20):
                await seed_default_pgc(session, empresa_id)
                session.add(
                    ConfiguracionFiscal(
                        empresa_id=empresa_id,
                        recargo_equivalencia_habilitado=False,
                        cuenta_recargo=None,
                        criterio_caja_habilitado=False,
                        tipo_is=Decimal("25.00"),
                        fecha_vigencia_desde=date(2000, 1, 1),
                        fecha_vigencia_hasta=None,
                    )
                )
                session.add_all(
                    [
                        FiscalYear(
                            empresa_id=empresa_id,
                            year=2025,
                            date_start=date(2025, 1, 1),
                            date_end=date(2025, 12, 31),
                            is_closed=True,
                        ),
                        FiscalYear(
                            empresa_id=empresa_id,
                            year=2026,
                            date_start=date(2026, 1, 1),
                            date_end=date(2026, 12, 31),
                            is_closed=False,
                        ),
                    ]
                )
                await session.flush()
                cuentas = {
                    cuenta.code: cuenta
                    for cuenta in (
                        await session.scalars(
                            _select(AccountPlan).where(
                                AccountPlan.tenant_id == empresa_id
                            )
                        )
                    ).all()
                }
                for ejercicio in (2025, 2026):
                    resultado_id = uuid.uuid4()
                    pagos_id = uuid.uuid4()
                    session.add_all(
                        [
                            JournalEntry(
                                id=resultado_id,
                                empresa_id=empresa_id,
                                ejercicio=ejercicio,
                                fecha=date(ejercicio, 12, 30),
                                tipo=JournalEntryTipo.GENERAL,
                                concepto="Resultado contable de prueba",
                                numero_asiento=1,
                                estado=JournalEntryEstado.POSTED,
                            ),
                            JournalEntry(
                                id=pagos_id,
                                empresa_id=empresa_id,
                                ejercicio=ejercicio,
                                fecha=date(ejercicio, 9, 20),
                                tipo=JournalEntryTipo.GENERAL,
                                concepto="Pago a cuenta de prueba",
                                numero_asiento=2,
                                estado=JournalEntryEstado.POSTED,
                            ),
                        ]
                    )
                    await session.flush()
                    session.add_all(
                        [
                            JournalEntryLine(
                                id=uuid.uuid4(),
                                empresa_id=empresa_id,
                                journal_entry_id=resultado_id,
                                account_id=cuentas["6210"].id,
                                line_no=1,
                                cuenta="6210",
                                debe=Decimal("20000.0000"),
                                haber=Decimal("0.0000"),
                            ),
                            JournalEntryLine(
                                id=uuid.uuid4(),
                                empresa_id=empresa_id,
                                journal_entry_id=resultado_id,
                                account_id=cuentas["7000"].id,
                                line_no=2,
                                cuenta="7000",
                                debe=Decimal("0.0000"),
                                haber=Decimal("120000.0000"),
                            ),
                            JournalEntryLine(
                                id=uuid.uuid4(),
                                empresa_id=empresa_id,
                                journal_entry_id=pagos_id,
                                account_id=cuentas["4730"].id,
                                line_no=1,
                                cuenta="4730",
                                debe=Decimal("20000.0000"),
                                haber=Decimal("0.0000"),
                            ),
                            JournalEntryLine(
                                id=uuid.uuid4(),
                                empresa_id=empresa_id,
                                journal_entry_id=pagos_id,
                                account_id=cuentas["5720"].id,
                                line_no=2,
                                cuenta="5720",
                                debe=Decimal("0.0000"),
                                haber=Decimal("20000.0000"),
                            ),
                            SecuenciaAsiento(
                                empresa_id=empresa_id,
                                ejercicio=ejercicio,
                                ultimo_numero=2,
                            ),
                        ]
                    )
                    await session.flush()
            await session.commit()
        return emit_token(1)

    loop = asyncio.new_event_loop()
    try:
        token = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
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

    def _headers(empresa_id: int = 10) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            token=token,
            factory=factory,
            headers=_headers,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            get=lambda empresa_id, ruta, **params: client.get(
                ruta, headers=_headers(empresa_id), params=params or None
            ),
            post=lambda ruta, empresa_id=10, json=None: client.post(
                ruta, headers=_headers(empresa_id), json=json
            ),
            patch=lambda ruta, empresa_id=10, json=None: client.patch(
                ruta, headers=_headers(empresa_id), json=json
            ),
            delete=lambda ruta, empresa_id=10: client.delete(
                ruta, headers=_headers(empresa_id)
            ),
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def catalogo_client():
    """HTTP client del catalogo versionado (SPEC-025): empresas A=10 y B=20,
    usuarios ADMIN/ACCOUNTANT/READ_ONLY, PGC base + cuenta 431, version base
    vigente 2025 (numero_version 1) por empresa y helpers de asientos."""
    import asyncio
    import types
    from datetime import date as _date

    from sqlalchemy import select as _select

    from api.catalogo import router as catalogo_router
    from models.acct.account_plan import AccountPlan
    from models.acct.fiscal_year import FiscalYear
    from models.catalog.catalogo_version import EstadoVersion
    from services.acct.seed import seed_default_pgc
    from services.catalog._comun import crear_version_completa
    from services.journal.entry_service import asentar as _asentar
    from services.journal.entry_service import crear_borrador as _crear_borrador

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

    async def _plantar_431(session, tenant_id: int) -> None:
        padre = await session.scalar(
            _select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id,
                AccountPlan.code == "43",
                AccountPlan.level == 2,
            )
        )
        if padre is None:
            return
        existente = await session.scalar(
            _select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id, AccountPlan.code == "431"
            )
        )
        if existente is None:
            session.add(
                AccountPlan(
                    tenant_id=tenant_id,
                    code="431",
                    level=3,
                    name="Clientes (otros)",
                    parent_id=padre.id,
                    is_selectable=False,
                )
            )
            await session.flush()

    async def _sembrar_version(session, tenant_id: int) -> str:
        version = await crear_version_completa(
            session,
            empresa_id=tenant_id,
            codigo="BASE-2025",
            fecha_inicio=_date(2025, 1, 1),
            fecha_fin=_date(2025, 12, 31),
            operaciones=[],
            mapeo_explicito=[],
            actor="seed",
        )
        version.estado = EstadoVersion.vigente
        await session.flush()
        return str(version.id)

    async def _setup() -> dict[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="admin@cat.es", password_hash=hash_password("pw"), full_name="Adm"),
                    User(id=2, email="cont@cat.es", password_hash=hash_password("pw"), full_name="Con"),
                    User(id=3, email="lec@cat.es", password_hash=hash_password("pw"), full_name="Lec"),
                ]
            )
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Catalogo Diez SL", 20: "Catalogo Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                await _plantar_431(session, tenant)
            ver10 = await _sembrar_version(session, 10)
            ver20 = await _sembrar_version(session, 20)
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
            "ver10": ver10,
            "ver20": ver20,
        }

    loop = asyncio.new_event_loop()
    try:
        datos = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(catalogo_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else datos[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _get(ruta: str, empresa_id: int = 10, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin", **kwargs):
        return client.post(
            ruta, headers=_hh(token_key, empresa_id), json=json, **kwargs
        )

    def _cuenta(empresa_id: int, code: str) -> int:
        async def _op(session):
            cuenta = await session.scalar(
                _select(AccountPlan).where(
                    AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
                )
            )
            assert cuenta is not None, f"cuenta {code} no sembrada para {empresa_id}"
            return cuenta.id

        return _run(consultar(_op))

    def _asiento(
        empresa_id: int,
        fecha,
        concepto: str,
        lineas: list[dict],
        tipo=None,
    ):
        async def _op(session):
            kwargs = {} if tipo is None else {"tipo": tipo}
            entrada = await _crear_borrador(
                session,
                empresa_id=empresa_id,
                fecha=fecha,
                concepto=concepto,
                lineas=lineas,
                actor="test",
                **kwargs,
            )
            await _asentar(
                session, empresa_id=empresa_id, entry_id=entrada.id, actor="test"
            )
            return entrada.id

        return _run(mutar(_op))

    def _marcar_cerrado(empresa_id: int = 10, year: int = 2025):
        async def _op(session):
            existente = await session.scalar(
                _select(FiscalYear).where(
                    FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
                )
            )
            if existente is None:
                session.add(
                    FiscalYear(
                        empresa_id=empresa_id,
                        year=year,
                        date_start=_date(year, 1, 1),
                        date_end=_date(year, 12, 31),
                        is_closed=True,
                    )
                )
            else:
                existente.is_closed = True
            await session.flush()

        return _run(mutar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            tokens=datos,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            cuenta=_cuenta,
            asiento=_asiento,
            marcar_cerrado=_marcar_cerrado,
            get=_get,
            post=_post,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def cashflow_client():
    """HTTP client de prevision/EFE/alertas (SPEC-027): empresas A=10 y B=20,
    usuarios ADMIN/ACCOUNTANT/READ_ONLY con matriz RBAC completa, PGC base y
    helpers de vencimientos, asientos y conciliacion."""
    import asyncio
    import types
    from datetime import date as _date

    from sqlalchemy import select as _select

    from api.tesoreria import router as tesoreria_router
    from models.treasury.conciliacion import Conciliacion, ConciliacionEstado
    from services.acct.seed import seed_default_pgc

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
                    User(id=1, email="admin@cf.es", password_hash=hash_password("pw"), full_name="Adm"),
                    User(id=2, email="cont@cf.es", password_hash=hash_password("pw"), full_name="Con"),
                    User(id=3, email="lec@cf.es", password_hash=hash_password("pw"), full_name="Lec"),
                ]
            )
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "C00000010", 20: "C00000020"},
                razones_sociales={10: "Tesorería Diez SL", 20: "Tesorería Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    loop = asyncio.new_event_loop()
    try:
        datos = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(tesoreria_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else datos[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _get(ruta: str, empresa_id: int = 10, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin", **kwargs):
        return client.post(
            ruta, headers=_hh(token_key, empresa_id), json=json, **kwargs
        )

    def _cuentas(empresa_id: int = 10) -> dict[str, int]:
        async def _op(session):
            filas = await session.execute(
                _select(AccountPlan.code, AccountPlan.id).where(
                    AccountPlan.tenant_id == empresa_id
                )
            )
            return {codigo: int(ident) for codigo, ident in filas.all()}

        return _run(consultar(_op))

    def _plantar(empresa_id: int, code: str, parent: str, name: str | None = None) -> str:
        """Planta una cuenta de nivel 4 apuntable y devuelve su id como texto."""

        async def _op(session):
            from tests.unit import cashflow_support as soporte

            return str(await soporte.plantar_cuenta(
                session, empresa_id=empresa_id, code=code, parent=parent, name=name
            ))

        return _run(mutar(_op))

    def _vencimientos(empresa_id: int = 10, especificaciones=()) -> list[str]:
        """Siembra vencimientos y devuelve sus ids como texto."""
        from datetime import date as _d

        def _fecha(valor):
            return _d.fromisoformat(valor) if isinstance(valor, str) else valor

        async def _op(session):
            from tests.unit import cashflow_support as soporte

            filas = []
            for indice, spec in enumerate(especificaciones, start=1):
                fila = await soporte.vencimiento(
                    session,
                    empresa_id=empresa_id,
                    fecha_vencimiento=_fecha(spec["fecha_vencimiento"]),
                    importe=spec.get("importe", "1000.0000"),
                    tipo=spec.get("tipo", "cobro"),
                    estado=spec.get("estado", "pendiente"),
                    acumulado=spec.get("acumulado", "0.0000"),
                    recibo_num=spec.get("recibo_num", f"R-{indice:03d}"),
                )
                filas.append(str(fila.id))
            return filas

        return _run(mutar(_op))

    def _asiento(empresa_id: int, fecha, lineas, concepto="Tesorería", tipo="GENERAL"):
        from datetime import date as _d

        def _fecha(valor):
            return _d.fromisoformat(valor) if isinstance(valor, str) else valor

        async def _op(session):
            from tests.unit import cashflow_support as soporte

            return str(
                await soporte.publicar_asiento(
                    session,
                    empresa_id=empresa_id,
                    fecha=_fecha(fecha),
                    lineas=lineas,
                    concepto=concepto,
                    tipo=tipo,
                )
            )

        return _run(mutar(_op))

    def _conciliacion(
        empresa_id: int = 10,
        cuenta_codigo: str = "5720",
        ejercicio: int = 2026,
        fecha_fin=None,
        saldo_banco: str = "0.0000",
        saldo_libros: str = "0.0000",
    ) -> None:
        from decimal import Decimal as _Decimal

        fecha_fin = fecha_fin or _date(ejercicio, 3, 31)
        banco = _Decimal(str(saldo_banco))
        libros = _Decimal(str(saldo_libros))

        async def _op(session):
            from tests.unit import cashflow_support as soporte

            mapa = await soporte.cuentas(session, empresa_id)
            session.add(
                Conciliacion(
                    empresa_id=empresa_id,
                    cuenta_id=mapa[cuenta_codigo],
                    ejercicio=ejercicio,
                    fecha_inicio=_date(ejercicio, 1, 1),
                    fecha_fin=fecha_fin,
                    saldo_banco=banco,
                    saldo_libros=libros,
                    diferencia=banco - libros,
                    estado=ConciliacionEstado.cerrada,
                )
            )
            await session.flush()

        return _run(mutar(_op))

    def _cerrar_ejercicio(empresa_id: int = 10, year: int = 2026) -> None:
        from models.acct.fiscal_year import FiscalYear

        async def _op(session):
            existente = await session.scalar(
                _select(FiscalYear).where(
                    FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
                )
            )
            if existente is None:
                session.add(
                    FiscalYear(
                        empresa_id=empresa_id,
                        year=year,
                        date_start=_date(year, 1, 1),
                        date_end=_date(year, 12, 31),
                        is_closed=True,
                    )
                )
            else:
                existente.is_closed = True
            await session.flush()

        return _run(mutar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            tokens=datos,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            cuentas=_cuentas,
            plantar=_plantar,
            vencimientos=_vencimientos,
            asiento=_asiento,
            conciliacion=_conciliacion,
            cerrar_ejercicio=_cerrar_ejercicio,
            get=_get,
            post=_post,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def presupuestos_client():
    """HTTP client de presupuestos y desviaciones (SPEC-026): empresas A=10 y
    B=20, usuarios ADMIN/ACCOUNTANT/READ_ONLY, PGC base y centro de coste por
    empresa, mas helpers de asientos reales y de ejercicio cerrado."""
    import asyncio
    import types
    from datetime import date as _date

    from sqlalchemy import select as _select

    from api.presupuestos import router as presupuestos_router
    from models.acct.account_plan import AccountPlan
    from models.acct.fiscal_year import FiscalYear
    from services.acct.seed import seed_default_pgc
    from services.journal.entry_service import asentar as _asentar
    from services.journal.entry_service import crear_borrador as _crear_borrador

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

    async def _plantar_centro(session, tenant_id: int) -> str:
        from models.costcenters.centro_coste import (
            CentroCoste,
            CentroEstado,
            CentroTipo,
        )

        centro = CentroCoste(
            empresa_id=tenant_id,
            codigo="CC-01",
            nombre="Departamento de produccion",
            tipo=CentroTipo.departamento,
            estado=CentroEstado.activo,
        )
        session.add(centro)
        await session.flush()
        return str(centro.id)

    async def _setup() -> dict[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="admin@pre.es", password_hash=hash_password("pw"), full_name="Adm"),
                    User(id=2, email="cont@pre.es", password_hash=hash_password("pw"), full_name="Con"),
                    User(id=3, email="lec@pre.es", password_hash=hash_password("pw"), full_name="Lec"),
                ]
            )
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Presupuestos Diez SL", 20: "Presupuestos Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            centros = {}
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                centros[tenant] = await _plantar_centro(session, tenant)
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
            "centro10": centros[10],
            "centro20": centros[20],
        }

    loop = asyncio.new_event_loop()
    try:
        datos = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(presupuestos_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else datos[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _get(ruta: str, empresa_id: int = 10, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin", **kwargs):
        return client.post(
            ruta, headers=_hh(token_key, empresa_id), json=json, **kwargs
        )

    def _cuenta(empresa_id: int, code: str) -> int:
        async def _op(session):
            cuenta = await session.scalar(
                _select(AccountPlan).where(
                    AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
                )
            )
            assert cuenta is not None, f"cuenta {code} no sembrada para {empresa_id}"
            return cuenta.id

        return _run(consultar(_op))

    def _asiento(empresa_id: int, fecha, lineas: list[dict], concepto: str = "Real de test"):
        async def _op(session):
            borrador = await _crear_borrador(
                session,
                empresa_id=empresa_id,
                fecha=fecha,
                concepto=concepto,
                lineas=lineas,
                actor="test",
            )
            await _asentar(
                session, empresa_id=empresa_id, entry_id=borrador.id, actor="test"
            )
            return str(borrador.id)

        return _run(mutar(_op))

    def _marcar_cerrado(empresa_id: int = 10, year: int = 2025):
        async def _op(session):
            existente = await session.scalar(
                _select(FiscalYear).where(
                    FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
                )
            )
            if existente is None:
                session.add(
                    FiscalYear(
                        empresa_id=empresa_id,
                        year=year,
                        date_start=_date(year, 1, 1),
                        date_end=_date(year, 12, 31),
                        is_closed=True,
                    )
                )
            else:
                existente.is_closed = True
            await session.flush()

        return _run(mutar(_op))

    def _centros(empresa_id: int = 10) -> dict[str, str]:
        from models.costcenters.centro_coste import CentroCoste

        async def _op(session):
            filas = await session.execute(
                _select(CentroCoste.id, CentroCoste.codigo).where(
                    CentroCoste.empresa_id == empresa_id
                )
            )
            return {codigo: str(ident) for ident, codigo in filas.all()}

        return _run(consultar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            tokens=datos,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            cuenta=_cuenta,
            centros=_centros,
            asiento=_asiento,
            marcar_cerrado=_marcar_cerrado,
            get=_get,
            post=_post,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()

@pytest.fixture
def closing_client():
    """HTTP client de cierres (SPEC-028): empresas A=10 y B=20, usuarios
    ADMIN/ACCOUNTANT/READ_ONLY con matriz RBAC completa, PGC base, ejercicios y
    helpers de asientos reales, periodos cerrados y solicitudes de reapertura."""
    import asyncio
    import types
    from datetime import date as _date

    from sqlalchemy import select as _select

    from api.closing import router as cierres_router
    from models.acct.fiscal_year import FiscalYear
    from services.acct.seed import seed_default_pgc

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
                    User(id=1, email="admin@cierres.es", password_hash=hash_password("pw"), full_name="Adm"),
                    User(id=2, email="cont@cierres.es", password_hash=hash_password("pw"), full_name="Con"),
                    User(id=3, email="lec@cierres.es", password_hash=hash_password("pw"), full_name="Lec"),
                ]
            )
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Cierres Diez SL", 20: "Cierres Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
                # El seed de SPEC-001 no crea la 129; el cierre anual la exige
                # para la regularizacion (mismo criterio que la fixture de
                # cuentas de SPEC-010).
                session.add(
                    AccountPlan(
                        tenant_id=tenant,
                        code="129",
                        name="Perdidas y ganancias",
                        parent_id=(
                            await session.scalar(
                                _select(AccountPlan.id).where(
                                    AccountPlan.tenant_id == tenant,
                                    AccountPlan.code == "12",
                                )
                            )
                        ),
                        level=3,
                        is_selectable=False,
                        is_active=True,
                    )
                )
                for anio in (2025, 2026, 2027):
                    session.add(
                        FiscalYear(
                            empresa_id=tenant,
                            year=anio,
                            date_start=_date(anio, 1, 1),
                            date_end=_date(anio, 12, 31),
                            is_closed=False,
                        )
                    )
            await session.flush()
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    loop = asyncio.new_event_loop()
    try:
        datos = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(cierres_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else datos[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _get(ruta: str, empresa_id: int = 10, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin", **kwargs):
        return client.post(ruta, headers=_hh(token_key, empresa_id), json=json, **kwargs)

    def _cuentas(empresa_id: int = 10) -> dict[str, int]:
        from tests.unit import closing_support as soporte

        return _run(consultar(lambda s: soporte.cuentas(s, empresa_id)))

    def _asiento(empresa_id: int, fecha, lineas, concepto="Cierre de test", tipo="GENERAL"):
        from tests.unit import closing_support as soporte

        def _fecha(valor):
            return _date.fromisoformat(valor) if isinstance(valor, str) else valor

        return _run(
            mutar(
                lambda s: soporte.publicar_asiento(
                    s,
                    empresa_id=empresa_id,
                    fecha=_fecha(fecha),
                    lineas=lineas,
                    concepto=concepto,
                    tipo=tipo,
                )
            )
        )

    def _cerrar_periodos(
        empresa_id: int = 10, ejercicio: int = 2026, meses=(), tipo: str = "MES"
    ) -> None:
        from tests.unit import closing_support as soporte

        _run(
            mutar(
                lambda s: soporte.cerrar_meses(
                    s, empresa_id=empresa_id, ejercicio=ejercicio, meses=list(meses), tipo=tipo
                )
            )
        )

    def _marcar_cerrado(empresa_id: int = 10, year: int = 2025):
        async def _op(session):
            fila = await session.scalar(
                _select(FiscalYear).where(
                    FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
                )
            )
            if fila is None:
                session.add(
                    FiscalYear(
                        empresa_id=empresa_id,
                        year=year,
                        date_start=_date(year, 1, 1),
                        date_end=_date(year, 12, 31),
                        is_closed=True,
                    )
                )
            else:
                fila.is_closed = True
            await session.flush()

        return _run(mutar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            tokens=datos,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            cuentas=_cuentas,
            asiento=_asiento,
            cerrar_periodos=_cerrar_periodos,
            marcar_cerrado=_marcar_cerrado,
            get=_get,
            post=_post,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def export_client():
    """HTTP client de exportaciones (SPEC-029): empresas A=10 y B=20, usuarios
    ADMIN/ACCOUNTANT/READ_ONLY con matriz RBAC completa, PGC base y un dataset
    minimo por empresa (terceros, serie, facturas, asientos de 2025 y 2026,
    vencimiento). Solo la empresa A tiene `ConfigSii` (US3)."""
    import asyncio
    import types
    import zipfile

    from api.export import router as export_router

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
                    User(id=1, email="admin@export.es", password_hash=hash_password("pw"), full_name="Adm"),
                    User(id=2, email="cont@export.es", password_hash=hash_password("pw"), full_name="Con"),
                    User(id=3, email="lec@export.es", password_hash=hash_password("pw"), full_name="Lec"),
                ]
            )
            await crear_empresas(
                session, 10, 20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Export Diez SL", 20: "Export Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            await session.flush()
            from tests.unit import export_support as soporte

            for tenant in (10, 20):
                await soporte.sembrar_tenant(session, tenant, con_sii=(tenant == 10))
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    loop = asyncio.new_event_loop()
    try:
        datos = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(export_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else datos[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _get(ruta: str, empresa_id: int = 10, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin", **kwargs):
        return client.post(ruta, headers=_hh(token_key, empresa_id), json=json, **kwargs)

    def _put(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin"):
        return client.put(ruta, headers=_hh(token_key, empresa_id), json=json)

    def _exportar(
        empresa_id: int = 10,
        tipo: str = "INTEGRAL",
        desde=None,
        hasta=None,
        token_key: str = "admin",
    ):
        cuerpo: dict[str, object] = {"tipo": tipo}
        if desde is not None:
            cuerpo["ejercicio_desde"] = desde
        if hasta is not None:
            cuerpo["ejercicio_hasta"] = hasta
        return _post("/api/v1/exportaciones", cuerpo, empresa_id, token_key)

    def _abrir(respuesta) -> dict[str, object]:
        """Extrae el ZIP de la respuesta de descarga como dict ruta -> bytes."""
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.headers["content-type"] == "application/zip"
        import io

        with zipfile.ZipFile(io.BytesIO(respuesta.content), "r") as archivo:
            return {nombre: archivo.read(nombre) for nombre in sorted(archivo.namelist())}
    # `raise_server_exceptions=False`: un fallo de generacion debe devolverse
    # como HTTP 500 (cabecera en estado `fallida`), no como excepcion de test.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield types.SimpleNamespace(
            client=client,
            tokens=datos,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            get=_get,
            post=_post,
            put=_put,
            exportar=_exportar,
            abrir=_abrir,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()

@pytest.fixture
def documentos_client():
    """HTTP client de documentos adjuntos al asiento (SPEC-030): empresas A=10 y
    B=20, usuarios ADMIN/ACCOUNTANT/READ_ONLY con matriz RBAC completa, PGC
    base y, por empresa, un asiento `DRAFT` y otro `POSTED` con lineas
    balanceadas (constitucion I: el cuadre se comprueba antes y despues de
    adjuntar y de dar de baja).

    Expone `subir()` para el multipart de US1 y `asiento(empresa_id, estado)`
    para clonar el asiento ancla de una empresa y usarlo en la otra, que es lo
    que hace posible el escenario de aislamiento S7 sin sembrarlo todo dos veces.
    """
    import asyncio
    import types
    from datetime import date as _date

    from api.documentos import router as documentos_router
    from models.acct.account_plan import AccountPlan
    from models.acct.journal import JournalEntry
    from services.acct.seed import seed_default_pgc
    from services.journal.entry_service import asentar as _asentar
    from services.journal.entry_service import crear_borrador as _crear_borrador

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

    # El motor de SPEC-002 nombra los importes `debit`/`credit` en el dict de
    # linea; `debe`/`haber` son los nombres de las columnas.
    LINEAS = [
        {"cuenta": "6000", "debit": "1210.0000", "credit": "0.0000", "detail": "Compra"},
        {"cuenta": "4100", "debit": "0.0000", "credit": "1210.0000", "detail": "Proveedor"},
    ]

    async def _crear_asiento(session, empresa_id: int, estado: str, numero: int) -> str:
        from sqlalchemy import select as _select

        from models.acct.account_plan import AccountPlan

        # `crear_borrador` exige el `account_id` real de cada linea.
        cuentas = {
            code: ident
            for ident, code in (
                await session.execute(
                    _select(AccountPlan.id, AccountPlan.code).where(
                        AccountPlan.tenant_id == empresa_id,
                        AccountPlan.code.in_(("6000", "4100")),
                    )
                )
            ).all()
        }
        lineas = []
        for linea in LINEAS:
            item = dict(linea)
            item["account_id"] = cuentas[item["cuenta"]]
            lineas.append(item)
        borrador = await _crear_borrador(
            session,
            empresa_id=empresa_id,
            fecha=_date(2026, 3, numero),
            concepto=f"Compra con soporte {estado}",
            lineas=lineas,
            actor="test",
        )
        if estado == "POSTED":
            await _asentar(
                session, empresa_id=empresa_id, entry_id=borrador.id, actor="test"
            )
        await session.flush()
        return str(borrador.id)

    async def _setup() -> dict[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)
        async with factory() as session:
            session.add_all(
                [
                    User(id=1, email="admin@doc.es", password_hash=hash_password("pw"), full_name="Adm"),
                    User(id=2, email="cont@doc.es", password_hash=hash_password("pw"), full_name="Con"),
                    User(id=3, email="lec@doc.es", password_hash=hash_password("pw"), full_name="Lec"),
                ]
            )
            await sembrar_empresas_pgc(
                session, 10, 20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Documentos Diez SL", 20: "Documentos Veinte SL"},
            )
            await session.flush()
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                    UserCompany(id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True),
                    UserCompany(id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT),
                    UserCompany(id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True),
                    UserCompany(id=6, user_id=3, company_id=20, role=UserRol.READ_ONLY),
                ]
            )
            for tenant in (10, 20):
                await seed_default_pgc(session, tenant)
            await session.commit()
            for tenant in (10, 20):
                await _crear_asiento(session, tenant, "DRAFT", 14)
                await _crear_asiento(session, tenant, "POSTED", 15)
            await session.commit()
        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    loop = asyncio.new_event_loop()
    try:
        datos = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(documentos_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else datos[token_key]
        return {
            "Authorization": f"Bearer {token}",
            "X-Empresa-Activa": str(empresa_id),
        }

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    def _get(ruta: str, empresa_id: int = 10, token_key: str = "admin", **params):
        return client.get(ruta, headers=_hh(token_key, empresa_id), params=params or None)

    def _post(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin", **kwargs):
        return client.post(ruta, headers=_hh(token_key, empresa_id), json=json, **kwargs)

    def _delete(ruta: str, json=None, empresa_id: int = 10, token_key: str = "admin"):
        # `TestClient.delete` no acepta `json=` como keyword: se pasa por
        # `request` o se serializa en `content` con la cabecera explicita.
        return client.request(
            "DELETE", ruta, headers=_hh(token_key, empresa_id), json=json
        )

    def _subir(
        ruta: str,
        empresa_id: int = 10,
        files: list | None = None,
        campos: dict | None = None,
        token_key: str = "admin",
    ):
        """POST multipart. `files` es la lista de `("files", (nombre, bytes, mime))`
        que exige httpx; el campo del formulario va en `campos`."""
        return client.post(
            ruta,
            headers=_hh(token_key, empresa_id),
            files=files or [],
            data=campos or {},
        )

    def _asiento(empresa_id: int = 10, estado: str = "DRAFT") -> str:
        """Id del asiento ancla de la empresa, ya sea DRAFT o POSTED."""
        async def _op(session):
            from sqlalchemy import select as _select

            fila = await session.execute(
                _select(JournalEntry.id, JournalEntry.estado)
                .where(
                    JournalEntry.empresa_id == empresa_id,
                    JournalEntry.estado == estado,
                )
                .order_by(JournalEntry.created_at, JournalEntry.id)
            )
            found = fila.first()
            assert found is not None, f"no hay asiento {estado} para {empresa_id}"
            return str(found[0])

        return _run(consultar(_op))

    def _asiento_nuevo(empresa_id: int = 10, estado: str = "DRAFT") -> str:
        """Crea un asiento nuevo (borrador por defecto) para no compartir el ancla."""
        numero = 20 if estado == "POSTED" else 21
        return _run(mutar(_crear_asiento(empresa_id, estado, numero)))

    def _cuadre(asiento_id: str, empresa_id: int = 10) -> dict[str, str]:
        """Suma de Debe y Haber del asiento: constitution I / FR-015 / SC-007."""
        import uuid
        from decimal import Decimal

        from models.acct.journal import JournalEntryLine

        async def _op(session):
            from sqlalchemy import func as _func
            from sqlalchemy import select as _select

            fila = await session.execute(
                _select(
                    _func.coalesce(_func.sum(JournalEntryLine.debe), 0),
                    _func.coalesce(_func.sum(JournalEntryLine.haber), 0),
                ).where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == uuid.UUID(asiento_id),
                )
            )
            debe, haber = fila.one()
            estado = await session.scalar(
                _select(JournalEntry.estado).where(
                    JournalEntry.empresa_id == empresa_id,
                    JournalEntry.id == uuid.UUID(asiento_id),
                )
            )
            return {
                "debe": f"{Decimal(str(debe)):0.4f}",
                "haber": f"{Decimal(str(haber)):0.4f}",
                "estado": estado.value if estado is not None else "",
            }

        return _run(consultar(_op))

    def _cuenta(empresa_id: int, code: str) -> int:
        async def _op(session):
            from sqlalchemy import select as _select

            cuenta = await session.scalar(
                _select(AccountPlan).where(
                    AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
                )
            )
            assert cuenta is not None, f"cuenta {code} no sembrada para {empresa_id}"
            return cuenta.id

        return _run(consultar(_op))

    def _documentos(asiento_id: str, empresa_id: int = 10) -> list:
        """Filas de `documento_asiento` del asiento, para comprobar el cuadre."""
        import uuid

        from models.acct.documento import DocumentoAsiento

        async def _op(session):
            from sqlalchemy import select as _select

            return (
                await session.scalars(
                    _select(DocumentoAsiento)
                    .where(
                        DocumentoAsiento.empresa_id == empresa_id,
                        DocumentoAsiento.journal_entry_id == uuid.UUID(asiento_id),
                    )
                    .order_by(DocumentoAsiento.created_at, DocumentoAsiento.id)
                )
            ).all()

        return _run(consultar(_op))

    with TestClient(app) as client:
        yield types.SimpleNamespace(
            client=client,
            tokens=datos,
            factory=factory,
            headers=_hh,
            run=_run,
            consultar=consultar,
            mutar=mutar,
            get=_get,
            post=_post,
            delete=_delete,
            subir=_subir,
            asiento=_asiento,
            asiento_nuevo=_asiento_nuevo,
            cuadre=_cuadre,
            cuenta=_cuenta,
            documentos=_documentos,
        )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


@pytest.fixture
def recon_client():
    """HTTP client del router de conciliacion bancaria (SPEC-013).

    Empresas A=10 y B=20 con el PGC base y un unico usuario ADMIN en las dos.
    Vive aqui y no en `tests/integration/test_conciliacion_http.py` porque lo usan
    tambien los tests del XLSX de banco: un fixture de un modulo de test no se
    importa desde otro (rompe la recoleccion con el modo `prepend`).
    """
    from api.reconciliation import router as reconciliation_router

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
            session.add(
                User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
            )
            await session.flush()
            # Las empresas antes que `user_companies`: la FK compuesta
            # `(user_id, company_id)` no tiene nada a lo que apuntar si no.
            await sembrar_empresa_pgc(session, 10)
            await sembrar_empresa_pgc(session, 20)
            session.add_all(
                [
                    UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
                    UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ADMIN),
                ]
            )
            await session.flush()
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


@pytest.fixture
def navegacion_client():
    """HTTP client de `GET /api/v1/contexto` (SPEC-031, US1).

    Empresas A=10 y B=20, usuarios ADMIN/ACCOUNTANT/READ_ONLY con matriz RBAC y
    PGC base. El montaje de ejercicios es lo que importa aqui, y esta pensado para
    que los casos del spec sean comprobables sin sembrar nada a mano:

    - **Empresa 10**: 2025 CERRADO (lo cierran las dos fuentes, para que el estado
      derivado sea inequivoco), 2025 con apertura en `EjercicioContable` pero
      abierto, 2026 abierto y con 2 asientos POSTED. Es el caso del 31 de
      diciembre: dos ejercicios a la vez.
    - **Empresa 20**: solo 2026, con 1 asiento. Deliberadamente un conjunto
      DISTINTO al de la empresa 10, para que un fallo de filtro por empresa se
      vea en el listado de ejercicios y en los contadores.

    Expone `get()`, `token_de(clave)` y `emitir_token(user_id)` para poder clonar
    el contexto de una empresa en la otra, que es lo que hace posible el escenario
    de aislamiento sin sembrarlo dos veces.
    """
    import asyncio
    import datetime as _dt

    from api.navigation import favoritos_router, resumenes_router
    from api.navigation import router as navigation_router
    from models.acct.fiscal_year import FiscalYear
    from models.acct.journal import JournalEntry, JournalEntryTipo

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

    def _asiento(
        sesion: AsyncSession, empresa: int, ejercicio: int, numero: int, mes: int = 3
    ) -> None:
        import uuid as _uuid

        sesion.add(
            JournalEntry(
                id=_uuid.uuid4(),
                empresa_id=empresa,
                ejercicio=ejercicio,
                numero_asiento=numero,
                fecha=_dt.date(ejercicio, mes, 15),
                concepto="Apunte de contexto",
                estado="POSTED",
                tipo=JournalEntryTipo.GENERAL,
            )
        )

    async def _setup() -> dict[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(instalar_triggers_sqlite)

        async with factory() as session:
            session.add_all(
                [
                    User(
                        id=1,
                        email="admin@nav.es",
                        password_hash=hash_password("pw"),
                        full_name="Adm",
                    ),
                    User(
                        id=2,
                        email="cont@nav.es",
                        password_hash=hash_password("pw"),
                        full_name="Con",
                    ),
                    User(
                        id=3,
                        email="lec@nav.es",
                        password_hash=hash_password("pw"),
                        full_name="Lec",
                    ),
                ]
            )
            await sembrar_empresas_pgc(
                session,
                10,
                20,
                nifs={10: "A00000010", 20: "B00000020"},
                razones_sociales={10: "Navegacion Diez SL", 20: "Navegacion Veinte SL"},
            )
            await session.flush()

            session.add_all(
                [
                    UserCompany(
                        id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True
                    ),
                    UserCompany(
                        id=2, user_id=1, company_id=20, role=UserRol.ADMIN, is_active=True
                    ),
                    UserCompany(
                        id=3, user_id=2, company_id=10, role=UserRol.ACCOUNTANT, is_default=True
                    ),
                    UserCompany(
                        id=4, user_id=2, company_id=20, role=UserRol.ACCOUNTANT, is_active=True
                    ),
                    UserCompany(
                        id=5, user_id=3, company_id=10, role=UserRol.READ_ONLY, is_default=True
                    ),
                ]
            )

            # --- Empresa 10: dos ejercicios, uno cerrado ---
            session.add_all(
                [
                    FiscalYear(
                        empresa_id=10,
                        year=2025,
                        date_start=_dt.date(2025, 1, 1),
                        date_end=_dt.date(2025, 12, 31),
                        is_closed=True,
                    ),
                    EjercicioContable(
                        empresa_id=10,
                        ejercicio=2025,
                        fecha_inicio=_dt.date(2025, 1, 1),
                        fecha_fin=_dt.date(2025, 12, 31),
                        estado=EjercicioEstado.cerrado,
                    ),
                    EjercicioContable(
                        empresa_id=10,
                        ejercicio=2026,
                        fecha_inicio=_dt.date(2026, 1, 1),
                        fecha_fin=_dt.date(2026, 12, 31),
                        estado=EjercicioEstado.abierto,
                    ),
                ]
            )

            # --- Empresa 20: un ejercicio que NO existe en la empresa 10 ---
            # 2024 esta aqui y solo aqui, a proposito: es el unico ano que permite
            # comprobar que una cabecera manipulada se rechaza por PERTENENCIA y no
            # por inexistencia. Sin el, todos los anos de la 20 existen tambien en la
            # 10 y el caso ajeno seria indistinguible del propio.
            session.add_all(
                [
                    EjercicioContable(
                        empresa_id=20,
                        ejercicio=2024,
                        fecha_inicio=_dt.date(2024, 4, 1),
                        fecha_fin=_dt.date(2025, 3, 31),
                        estado=EjercicioEstado.abierto,
                    ),
                    EjercicioContable(
                        empresa_id=20,
                        ejercicio=2026,
                        fecha_inicio=_dt.date(2026, 4, 1),
                        fecha_fin=_dt.date(2027, 3, 31),
                        estado=EjercicioEstado.abierto,
                    ),
                ]
            )

            await session.flush()
            _asiento(session, 10, 2026, 1, mes=2)
            _asiento(session, 10, 2026, 2, mes=7)
            _asiento(session, 10, 2025, 1, mes=11)
            _asiento(session, 20, 2026, 1, mes=5)
            await session.commit()

        return {
            "admin": emit_token(1),
            "accountant": emit_token(2),
            "readonly": emit_token(3),
        }

    loop = asyncio.new_event_loop()
    try:
        datos = loop.run_until_complete(_setup())
    finally:
        loop.close()

    app = FastAPI()
    app.include_router(navigation_router)
    # Los favoritos (US4) cuelgan de su propio router con otro prefijo, asi que hay que
    # montarlo explicitamente. Montar solo `navigation_router` daria 404 en las cuatro
    # rutas de favoritos y el fallo pareceria del servicio.
    app.include_router(favoritos_router)
    # Los resúmenes (US5) también cuelgan de su propio prefijo. Sin montarlo aquí, los
    # tests de aislamiento de superficies darían 404 y parecería un fallo del servicio.
    app.include_router(resumenes_router)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    def _hh(token_key: str = "admin", empresa_id: int = 10) -> dict[str, str]:
        token = token_key if len(token_key) > 20 else datos[token_key]
        cabeceras = {"Authorization": f"Bearer {token}"}
        if empresa_id is not None:
            cabeceras["X-Empresa-Activa"] = str(empresa_id)
        return cabeceras

    def get(
        ruta: str,
        empresa_id: int = 10,
        token_key: str = "admin",
        ejercicio: int | str | None = None,
        **params,
    ):
        cabeceras = _hh(token_key, empresa_id)
        if ejercicio is not None:
            cabeceras["X-Ejercicio-Activa"] = str(ejercicio)
        return client.get(ruta, headers=cabeceras, params=params or None)

    def _escribir(metodo, ruta, empresa_id, token_key, **kw):
        """Un solo verbo para PUT/PATCH/POST/DELETE.

        Se evita un helper por verbo porque los cuatro comparten la misma regla de
        cabeceras, y cuatro copias de esas reglas serian cuatro sitios donde forget la
        cabecera de empresa. En `DELETE` no se manda cuerpo, que es lo que espera el
        endpoint de desmarcar.
        """
        cabeceras = _hh(token_key, empresa_id)
        return client.request(metodo, ruta, headers=cabeceras, **kw)

    def post(ruta, empresa_id=10, token_key="admin", **body):
        return _escribir("POST", ruta, empresa_id, token_key, json=body)

    def put(ruta, empresa_id=10, token_key="admin", **body):
        return _escribir("PUT", ruta, empresa_id, token_key, json=body)

    def patch(ruta, empresa_id=10, token_key="admin", **body):
        return _escribir("PATCH", ruta, empresa_id, token_key, json=body)

    def delete(ruta, empresa_id=10, token_key="admin"):
        return _escribir("DELETE", ruta, empresa_id, token_key)

    def _run(coro):
        loop_ = asyncio.new_event_loop()
        try:
            return loop_.run_until_complete(coro)
        finally:
            loop_.close()

    async def consultar(func):
        async with factory() as session:
            return await func(session)

    async def mutar(func):
        async with factory() as session:
            resultado = await func(session)
            await session.commit()
            return resultado

    return types.SimpleNamespace(
        client=client,
        get=get,
        post=post,
        put=put,
        patch=patch,
        delete=delete,
        datos=datos,
        consultar=consultar,
        mutar=mutar,
        run=_run,
        token_de=lambda clave: datos[clave],
        token_para_usuario=emit_token,
    )
