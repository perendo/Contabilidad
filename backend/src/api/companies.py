"""Companies router (SPEC-003): list only accessible, active companies."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from models.iam.user import User
from services.auth.company_service import crear_empresa
from services.auth.session import listar_empresas_usuario

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


class CompanyCreate(BaseModel):
    nif: str = Field(min_length=1, max_length=20)
    razon_social: str = Field(min_length=1, max_length=200)


@router.get("")
async def listar_empresas(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    items = await listar_empresas_usuario(db, user.id)
    return {"items": items}


@router.post("", status_code=status.HTTP_201_CREATED)
async def alta_empresa(
    body: CompanyCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ip = request.client.host if request.client else None
    company, _ = await crear_empresa(
        db, user_id=user.id, nif=body.nif, razon_social=body.razon_social, ip=ip
    )
    return {
        "company_id": company.company_id,
        "nif": company.nif,
        "razon_social": company.razon_social,
        "role": "ADMIN",
        "default_company_id": company.company_id,
    }