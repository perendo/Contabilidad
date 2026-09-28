"""Auth router (SPEC-003 US1): POST /api/v1/auth/login, GET /me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from models.iam.user import User
from services.auth.session import (
    AccesoDenegadoError,
    LoginError,
    empresa_por_defecto,
    listar_empresas_usuario,
    login,
    switch_company,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


def _sesion_payload(
    user: User,
    companies: list[dict],
    default_company_id: int | None,
) -> dict:
    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
        "default_company_id": default_company_id,
        "companies": companies,
    }


@router.post("/login")
async def login_endpoint(
    body: LoginBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ip = request.client.host if request.client else None
    try:
        user, token, companies, default_id = await login(
            db, email=body.email, password=body.password, ip=ip
        )
    except LoginError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )
    return {"token": token, **_sesion_payload(user, companies, default_id)}


@router.get("/me")
async def me_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    companies = await listar_empresas_usuario(db, user.id)
    default_id = await empresa_por_defecto(db, user.id)
    return _sesion_payload(user, companies, default_id)


class SwitchBody(BaseModel):
    company_id: int = Field(gt=0)


@router.post("/switch-company")
async def switch_company_endpoint(
    body: SwitchBody,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ip = request.client.host if request.client else None
    try:
        ctx = await switch_company(db, user_id=user.id, company_id=body.company_id, ip=ip)
    except AccesoDenegadoError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a la empresa solicitada",
        )
    return ctx