"""Session services: login, accessible companies and switch (SPEC-003 US1)."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany
from services.audit.writer import audit_escribir
from services.auth.security import emit_token, verify_password


class LoginError(Exception):
    pass


class AccesoDenegadoError(Exception):
    pass


def _email_fingerprint(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]


async def listar_empresas_usuario(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """Companies accessible to a user: active relation AND active company only."""
    filas = (
        await db.execute(
            select(UserCompany, Company)
            .join(Company, Company.company_id == UserCompany.company_id)
            .where(UserCompany.user_id == user_id, UserCompany.is_active.is_(True))
            .where(Company.is_active.is_(True))
            .order_by(Company.company_id)
        )
    ).all()
    return [
        {
            "company_id": rel.company_id,
            "nif": company.nif,
            "razon_social": company.razon_social,
            "role": rel.role.value,
            "is_default": rel.is_default,
        }
        for rel, company in filas
    ]


async def empresa_por_defecto(db: AsyncSession, user_id: int) -> int | None:
    rel = await db.scalar(
        select(UserCompany).where(
            UserCompany.user_id == user_id,
            UserCompany.is_default.is_(True),
            UserCompany.is_active.is_(True),
        )
    )
    if rel is None:
        return None
    company = await db.get(Company, rel.company_id)
    if company is None or not company.is_active:
        return None
    return rel.company_id


async def login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    ip: str | None = None,
) -> tuple[User, str, list[dict[str, Any]], int | None]:
    """Authenticate a user and return (user, token, companies, default_company_id).

    LOGIN_FAILED audits only an email fingerprint (never reveals existence).
    """
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    valid = user is not None and user.is_active and verify_password(password, user.password_hash)
    if not valid:
        await audit_escribir(
            db,
            empresa_id=None,
            actor=_email_fingerprint(email),
            action="LOGIN_FAILED",
            entity="auth",
            ip=ip,
        )
        await db.flush()
        raise LoginError("Credenciales inválidas")

    assert user is not None
    token = emit_token(user.id)
    companies = await listar_empresas_usuario(db, user.id)
    default_id = await empresa_por_defecto(db, user.id)
    await audit_escribir(
        db,
        empresa_id=default_id,
        actor=user.email,
        action="LOGIN",
        entity="auth",
        entity_id=user.id,
        ip=ip,
    )
    await db.flush()
    return user, token, companies, default_id
async def switch_company(
    db: AsyncSession,
    *,
    user_id: int,
    company_id: int,
    ip: str | None = None,
) -> dict[str, Any]:
    """Revalida la relación activa con la empresa pedida y audita SWITCH_COMPANY.

    El contexto nunca se confía al cliente: se valida contra user_companies en
    cada petición (403 equivalente sin revelar existencia).
    """
    fila = (
        await db.execute(
            select(UserCompany, Company)
            .join(Company, Company.company_id == UserCompany.company_id)
            .where(
                UserCompany.user_id == user_id,
                UserCompany.company_id == company_id,
                UserCompany.is_active.is_(True),
                Company.is_active.is_(True),
            )
        )
    ).first()
    if fila is None:
        raise AccesoDenegadoError("Sin acceso a la empresa solicitada")
    rel, company = fila
    user = await db.get(User, user_id)
    actor = user.email if user else None
    await audit_escribir(
        db,
        empresa_id=company_id,
        actor=actor or "system",
        action="SWITCH_COMPANY",
        entity="user_company",
        entity_id=rel.id,
        ip=ip,
        payload={"desde_rol": rel.role.value},
    )
    await db.flush()
    return {
        "company_id": company.company_id,
        "razon_social": company.razon_social,
        "role": rel.role.value,
    }
