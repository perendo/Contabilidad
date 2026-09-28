"""Tests SPEC-003 US2 (T019): switch sin acceso → 403 sin alterar el contexto."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit.audit_log import AuditLog
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import hash_password
from services.auth.session import (
    AccesoDenegadoError,
    empresa_por_defecto,
    listar_empresas_usuario,
    switch_company,
)
from tests.conftest import crear_empresas


async def _escenario(db: AsyncSession) -> int:
    db.add(User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana"))
    await crear_empresas(
        db, 10, 20, 30,
        nifs={10: "A00000001", 20: "B00000002", 30: "C00000003"},
        razones_sociales={10: "Diez SL", 20: "Veinte SL", 30: "Treinta SL"},
        inactivos=(30,),
    )
    await db.flush()
    db.add_all(
        [
            UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
            UserCompany(id=2, user_id=1, company_id=20, role=UserRol.ACCOUNTANT),
            UserCompany(id=3, user_id=1, company_id=30, role=UserRol.ADMIN),
        ]
    )
    await db.flush()
    return 1


async def test_switch_sin_relacion_no_altera_contexto(db_session: AsyncSession) -> None:
    user_id = await _escenario(db_session)
    antes = await listar_empresas_usuario(db_session, user_id)
    with pytest.raises(AccesoDenegadoError):
        await switch_company(db_session, user_id=user_id, company_id=999)
    assert await listar_empresas_usuario(db_session, user_id) == antes
    assert await empresa_por_defecto(db_session, user_id) == 10
    regs = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.operacion == "SWITCH_COMPANY")
        )
    ).all()
    assert regs == []


async def test_switch_empresa_inactiva_denegado(db_session: AsyncSession) -> None:
    user_id = await _escenario(db_session)
    with pytest.raises(AccesoDenegadoError):
        await switch_company(db_session, user_id=user_id, company_id=30)
    assert await empresa_por_defecto(db_session, user_id) == 10
