"""Tests SPEC-003 US4 (T028): fallo del seed revierte el alta completa."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany
from services.auth import company_service
from services.auth.company_service import crear_empresa
from services.auth.security import hash_password


async def _usuario(db: AsyncSession) -> None:
    db.add(User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana"))
    await db.flush()


async def test_fallo_seed_no_persiste_empresa(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _usuario(db_session)

    async def _seed_roto(db: AsyncSession, tenant_id: int) -> int:
        raise RuntimeError("seed roto")

    monkeypatch.setattr(company_service, "seed_default_pgc", _seed_roto)
    with pytest.raises(RuntimeError, match="seed roto"):
        await crear_empresa(db_session, user_id=1, nif="B12345678", razon_social="Nueva SL")
    await db_session.rollback()
    assert (await db_session.scalars(select(Company))).all() == []
    assert (await db_session.scalars(select(UserCompany))).all() == []


async def test_segundo_alta_reemplaza_defecto(db_session: AsyncSession) -> None:
    await _usuario(db_session)
    primera, _ = await crear_empresa(db_session, user_id=1, nif="A1", razon_social="Una SL")
    segunda, rel2 = await crear_empresa(db_session, user_id=1, nif="A2", razon_social="Dos SL")
    assert rel2.is_default is True
    rels = (await db_session.scalars(select(UserCompany).where(UserCompany.user_id == 1))).all()
    por_defecto = [r for r in rels if r.is_default]
    assert [(r.company_id) for r in por_defecto] == [segunda.company_id]
    assert primera.company_id != segunda.company_id
