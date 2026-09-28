"""Tests SPEC-003 Foundational (T012): aislamiento multi-tenant del modelo IAM."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import hash_password
from services.auth.session import (
    AccesoDenegadoError,
    empresa_por_defecto,
    listar_empresas_usuario,
)
from tests.conftest import crear_empresas


async def _escenario(db: AsyncSession) -> tuple[int, int]:
    db.add(User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana"))
    db.add(User(id=2, email="luis@x.es", password_hash=hash_password("pw"), full_name="Luis"))
    await crear_empresas(
        db, 10, 20,
        nifs={10: "A00000001", 20: "B00000002"},
        razones_sociales={10: "Diez SL", 20: "Veinte SL"},
    )
    await db.flush()
    db.add_all(
        [
            UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True),
            UserCompany(id=2, user_id=2, company_id=20, role=UserRol.ACCOUNTANT, is_default=True),
        ]
    )
    await db.flush()
    return 1, 2


async def test_contexto_a_no_filtra_datos_de_b(db_session: AsyncSession) -> None:
    ana, luis = await _escenario(db_session)
    empresas_ana = await listar_empresas_usuario(db_session, ana)
    empresas_luis = await listar_empresas_usuario(db_session, luis)
    assert [e["company_id"] for e in empresas_ana] == [10]
    assert [e["company_id"] for e in empresas_luis] == [20]
    assert await empresa_por_defecto(db_session, ana) == 10
    assert await empresa_por_defecto(db_session, luis) == 20


async def test_cross_tenant_denegado(db_session: AsyncSession) -> None:
    from services.auth.session import switch_company

    ana, _ = await _escenario(db_session)
    with pytest.raises(AccesoDenegadoError):
        await switch_company(db_session, user_id=ana, company_id=20)


async def test_relacion_inactiva_no_visible(db_session: AsyncSession) -> None:
    ana, _ = await _escenario(db_session)
    db_session.add(
        UserCompany(
            id=3, user_id=ana, company_id=20, role=UserRol.READ_ONLY, is_active=False
        )
    )
    await db_session.flush()
    empresas = await listar_empresas_usuario(db_session, ana)
    assert [e["company_id"] for e in empresas] == [10]
