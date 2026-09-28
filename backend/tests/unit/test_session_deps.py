"""Session dependency tests: empresa_id comes from the authenticated session (T004).

The shared guard (SPEC-003) derives the company from the JWT identity plus
the `X-Empresa-Activa` header validated against the user's active relations —
never from client-controlled request state or payloads.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from api.deps import get_empresa_id
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import emit_token, hash_password
from tests.conftest import crear_empresa


async def _escenario(db: AsyncSession) -> tuple[User, str]:
    user = User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
    db.add(user)
    await crear_empresa(db, 7, nif="A00000007", razon_social="Siete SL")
    await db.flush()
    db.add(
        UserCompany(id=1, user_id=user.id, company_id=7, role=UserRol.ADMIN, is_default=True)
    )
    await db.flush()
    return user, emit_token(user.id)


def _request(token: str | None = None, empresa: str | None = None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    if empresa is not None:
        headers.append((b"x-empresa-activa", empresa.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


async def test_empresa_de_sesion_autenticada(db_session: AsyncSession) -> None:
    user, token = await _escenario(db_session)
    assert await get_empresa_id(_request(token, "7"), db_session, user) == 7


async def test_sin_token_401(db_session: AsyncSession) -> None:
    from api.deps import get_current_user

    with pytest.raises(HTTPException) as exc:
        await get_current_user(_request(), db_session)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("empresa", [None, "abc", "0", "-3", "999"])
async def test_contexto_invalido_o_sin_acceso_403(
    db_session: AsyncSession, empresa: str | None
) -> None:
    user, token = await _escenario(db_session)
    with pytest.raises(HTTPException) as exc:
        await get_empresa_id(_request(token, empresa), db_session, user)
    assert exc.value.status_code == 403
