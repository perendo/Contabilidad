"""Endpoint tests for tercero amendments: condiciones and mandatos (T011)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

import models.treasury  # noqa: F401  (register tables on Base.metadata)
from api.treasury.routes import router
from database import get_db
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from models.treasury import CondicionProntoPago
from services.auth.security import emit_token, hash_password

TERCERO = str(uuid.uuid4())


@pytest.fixture
def client(db_session_factory):
    async def _sembrar_auth() -> str:
        async with db_session_factory() as session:
            session.add(
                User(id=98, email="terceros@x.es", password_hash=hash_password("pw"), full_name="Ter")
            )
            for cid in (42, 43, 44):
                session.add(
                    Company(company_id=cid, nif=f"U{cid:08d}", razon_social=f"Empresa {cid} SL")
                )
            await session.flush()
            for rid, cid in enumerate((42, 43, 44), start=200):
                session.add(
                    UserCompany(id=rid, user_id=98, company_id=cid, role=UserRol.ADMIN, is_default=(cid == 42))
                )
            await session.commit()
        return emit_token(98)

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

    def _hh(empresa_id: int) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa_id)}

    with TestClient(app) as test_client:
        yield test_client, {"hh": _hh}


def _correr(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def test_crear_y_parchear_condicion(client):
    test_client, auth = client
    hh = auth["hh"]
    created = test_client.post(
        f"/api/v1/terceros/{TERCERO}/condiciones",
        json={"plazo_dias": 10, "porcentaje": "2.00", "vigente": True},
        headers=hh(42),
    )
    assert created.status_code == 201
    condicion_id = created.json()["id"]
    assert created.json()["plazo_dias"] == 10
    assert created.json()["porcentaje"] == "2.00"

    patched = test_client.patch(
        f"/api/v1/terceros/condiciones/{condicion_id}",
        json={"plazo_dias": 5, "porcentaje": "3.00"},
        headers=hh(42),
    )
    assert patched.status_code == 200
    assert patched.json()["plazo_dias"] == 5
    assert patched.json()["porcentaje"] == "3.00"


async def test_crear_condicion_vigente_desactiva_la_previa(client, db_session_factory):
    test_client, auth = client
    hh = auth["hh"]
    primera = test_client.post(
        f"/api/v1/terceros/{TERCERO}/condiciones",
        json={"plazo_dias": 10, "porcentaje": "2.00", "vigente": True},
        headers=hh(42),
    )
    assert primera.status_code == 201
    segunda = test_client.post(
        f"/api/v1/terceros/{TERCERO}/condiciones",
        json={"plazo_dias": 8, "porcentaje": "1.50", "vigente": True},
        headers=hh(42),
    )
    assert segunda.status_code == 201

    async with db_session_factory() as session:
        condiciones = (
            await session.scalars(
                select(CondicionProntoPago).where(
                    CondicionProntoPago.empresa_id == 42,
                    CondicionProntoPago.tercero_id == uuid.UUID(TERCERO),
                )
            )
        ).all()
    assert sum(1 for c in condiciones if c.vigente) == 1


async def test_condicion_de_otra_empresa_no_es_visible(client):
    test_client, auth = client
    hh = auth["hh"]
    creada_a = test_client.post(
        f"/api/v1/terceros/{TERCERO}/condiciones",
        json={"plazo_dias": 10, "porcentaje": "2.00", "vigente": True},
        headers=hh(42),
    )
    condicion_a = creada_a.json()["id"]

    respuesta = test_client.patch(
        f"/api/v1/terceros/condiciones/{condicion_a}",
        json={"vigente": False},
        headers=hh(43),
    )
    assert respuesta.status_code == 404


async def test_crear_y_parchear_mandato(client):
    test_client, auth = client
    hh = auth["hh"]
    creado = test_client.post(
        f"/api/v1/terceros/{TERCERO}/mandatos",
        json={"mandato_ref": "MAND-2026-001", "fecha_firma": "2026-09-15", "tipo": "B2B"},
        headers=hh(42),
    )
    assert creado.status_code == 201
    mandato_id = creado.json()["id"]
    assert creado.json()["estado"] == "firmado"
    assert creado.json()["tipo"] == "B2B"

    revocado = test_client.patch(
        f"/api/v1/terceros/mandatos/{mandato_id}",
        json={"estado": "revocado"},
        headers=hh(42),
    )
    assert revocado.status_code == 200
    assert revocado.json()["estado"] == "revocado"


async def test_mandato_duplicado_rechazado(client, db_session_factory):
    test_client, auth = client
    hh = auth["hh"]
    payload = {"mandato_ref": "MAND-DUP", "fecha_firma": "2026-09-15", "tipo": "CORE"}
    assert test_client.post(f"/api/v1/terceros/{TERCERO}/mandatos", json=payload, headers=hh(42)).status_code == 201
    duplicado = test_client.post(f"/api/v1/terceros/{TERCERO}/mandatos", json=payload, headers=hh(42))
    assert duplicado.status_code == 409


async def test_mandato_de_otra_empresa_no_es_visible(client):
    test_client, auth = client
    hh = auth["hh"]
    creado = test_client.post(
        f"/api/v1/terceros/{TERCERO}/mandatos",
        json={"mandato_ref": "MAND-EMP", "fecha_firma": "2026-09-15", "tipo": "CORE"},
        headers=hh(42),
    )
    mandato_a = creado.json()["id"]

    respuesta = test_client.patch(
        f"/api/v1/terceros/mandatos/{mandato_a}",
        json={"estado": "revocado"},
        headers=hh(44),
    )
    assert respuesta.status_code == 404