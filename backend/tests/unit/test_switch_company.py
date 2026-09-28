"""Tests SPEC-003 US2 (T018): switch de empresa activa sin re-login."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import hash_password
from services.auth.session import AccesoDenegadoError, switch_company


async def _crear_escenario(db: AsyncSession) -> tuple[User, int, int, int]:
    user = User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
    db.add(user)
    await db.flush()
    empresas = [
        Company(company_id=10, nif="A00000001", razon_social="Diez SL"),
        Company(company_id=20, nif="B00000002", razon_social="Veinte SL"),
        Company(company_id=30, nif="C00000003", razon_social="Treinta SL", is_active=False),
    ]
    db.add_all(empresas)
    await db.flush()
    db.add_all(
        [
            UserCompany(id=1, user_id=user.id, company_id=10, role=UserRol.ADMIN, is_default=True),
            UserCompany(id=2, user_id=user.id, company_id=20, role=UserRol.ACCOUNTANT),
            UserCompany(id=3, user_id=user.id, company_id=30, role=UserRol.ADMIN),
        ]
    )
    await db.flush()
    return user, 10, 20, 30


async def test_switch_correcto(db_session: AsyncSession) -> None:
    user, _origen, destino, _ = await _crear_escenario(db_session)
    ctx = await switch_company(db_session, user_id=user.id, company_id=destino)
    assert ctx["company_id"] == destino
    assert ctx["role"] == "ACCOUNTANT"
    assert ctx["razon_social"] == "Veinte SL"


async def test_switch_sin_relacion(db_session: AsyncSession) -> None:
    user, _origen, _, _ = await _crear_escenario(db_session)
    with pytest.raises(AccesoDenegadoError):
        await switch_company(db_session, user_id=user.id, company_id=999)


async def test_switch_empresa_inactiva(db_session: AsyncSession) -> None:
    user, _origen, _, inactiva = await _crear_escenario(db_session)
    with pytest.raises(AccesoDenegadoError):
        await switch_company(db_session, user_id=user.id, company_id=inactiva)


async def test_switch_audita_en_la_misma_transaccion(db_session: AsyncSession) -> None:
    from models.audit.audit_log import AuditLog

    user, _origen, destino, _ = await _crear_escenario(db_session)
    await switch_company(db_session, user_id=user.id, company_id=destino)
    reg = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.operacion == "SWITCH_COMPANY",
                AuditLog.empresa_id == destino,
                AuditLog.usuario == user.email,
            )
        )
    ).all()
    assert len(reg) == 1
