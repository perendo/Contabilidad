"""Tests SPEC-003 US1 (T014): login inválido → 401 sin fugas de información."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit.audit_log import AuditLog
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import hash_password
from services.auth.session import LoginError, login
from tests.conftest import crear_empresa


async def _escenario(db: AsyncSession) -> None:
    db.add(User(id=1, email="ana@x.es", password_hash=hash_password("secret"), full_name="Ana"))
    db.add(
        User(
            id=2,
            email="bloqueado@x.es",
            password_hash=hash_password("secret"),
            full_name="Bloq",
            is_active=False,
        )
    )
    await crear_empresa(db, 10, nif="A00000001", razon_social="Diez SL")
    await db.flush()
    db.add(
        UserCompany(id=1, user_id=1, company_id=10, role=UserRol.ADMIN, is_default=True)
    )
    await db.flush()


async def test_password_incorrecta_no_filtra_empresas(db_session: AsyncSession) -> None:
    await _escenario(db_session)
    with pytest.raises(LoginError) as exc:
        await login(db_session, email="ana@x.es", password="otra")
    assert "10" not in str(exc.value) and "Diez" not in str(exc.value)


async def test_usuario_inexistente_mismo_error(db_session: AsyncSession) -> None:
    await _escenario(db_session)
    with pytest.raises(LoginError, match="Credenciales inválidas"):
        await login(db_session, email="nadie@x.es", password="secret")


async def test_usuario_inactivo_rechazado(db_session: AsyncSession) -> None:
    await _escenario(db_session)
    with pytest.raises(LoginError, match="Credenciales inválidas"):
        await login(db_session, email="bloqueado@x.es", password="secret")


async def test_fallo_audita_sin_datos_reveladores(db_session: AsyncSession) -> None:
    await _escenario(db_session)
    with pytest.raises(LoginError):
        await login(db_session, email="ana@x.es", password="otra")
    regs = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.operacion == "LOGIN_FAILED")
        )
    ).all()
    assert len(regs) == 1
    assert regs[0].usuario != "ana@x.es"
    assert "secret" not in str(regs[0].payload or "")
