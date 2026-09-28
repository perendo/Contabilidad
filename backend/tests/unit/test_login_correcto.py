"""Tests SPEC-003 US1 (T013): login correcto devuelve sesión completa."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit.audit_log import AuditLog
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import hash_password, verify_token
from services.auth.session import empresa_por_defecto, login
from tests.conftest import crear_empresas


async def _escenario(db: AsyncSession) -> None:
    db.add(User(id=1, email="ana@x.es", password_hash=hash_password("secret"), full_name="Ana"))
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
            UserCompany(id=2, user_id=1, company_id=20, role=UserRol.READ_ONLY),
            UserCompany(id=3, user_id=1, company_id=30, role=UserRol.ADMIN),
        ]
    )
    await db.flush()


async def test_login_devuelve_token_empresas_y_defecto(db_session: AsyncSession) -> None:
    await _escenario(db_session)
    user, token, companies, default_id = await login(
        db_session, email="ana@x.es", password="secret", ip="127.0.0.1"
    )
    assert user.email == "ana@x.es"
    assert verify_token(token) == user.id
    assert default_id == 10
    assert await empresa_por_defecto(db_session, user.id) == 10
    por_id = {c["company_id"]: c for c in companies}
    assert set(por_id) == {10, 20}
    assert por_id[10]["role"] == "ADMIN"
    assert por_id[10]["is_default"] is True
    assert por_id[20]["role"] == "READ_ONLY"


async def test_login_audita_en_la_misma_transaccion(db_session: AsyncSession) -> None:
    await _escenario(db_session)
    user, _, _, _ = await login(db_session, email="ana@x.es", password="secret")
    regs = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.operacion == "LOGIN",
                AuditLog.usuario == user.email,
            )
        )
    ).all()
    assert len(regs) == 1
