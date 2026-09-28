"""Account-plan router (SPEC-001 US1+US2+US3+US4): tree, suggest, create, update."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from services.acct.account_service import (
    AccountError,
    SuggestError,
    actualizar_cuenta,
    crear_cuenta,
    suggest,
)
from services.acct.plan_tree import build_tree, obtener_cuenta

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


class CuentaCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=8, pattern=r"^\d+$")
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: int | None = None


class CuentaUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None


class CuentaResponse(BaseModel):
    id: int
    code: str
    name: str
    level: int
    is_selectable: bool
    is_active: bool


@router.get("/tree", dependencies=[Depends(require_permission("acct", "ver"))])
async def arbol(
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    nodos = await build_tree(db, empresa_id)
    return {"nodos": nodos}


@router.get("/suggest", dependencies=[Depends(require_permission("acct", "ver"))])
async def sugerir(
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, description="Fragmento de código o nombre")],
    limit: Annotated[int, Query(ge=1, le=50, description="Máximo resultados")] = 20,
):
    try:
        items = await suggest(db, empresa_id, q, limit=limit)
    except SuggestError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    return {"items": items}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "crear"))],
)
async def crear(
    data: CuentaCreate,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        cuenta = await crear_cuenta(db, empresa_id, data.code, data.name, data.parent_id)
    except AccountError as e:
        if e.code == "code_duplicate":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        if e.code in ("parent_not_found", "parent_inactive"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        if e.code in ("parent_level_max", "level_mismatch", "code_prefix_mismatch", "level_max", "code_not_numeric", "code_too_long"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CuentaResponse(
        id=cuenta.id,
        code=cuenta.code,
        name=cuenta.name,
        level=cuenta.level,
        is_selectable=cuenta.is_selectable,
        is_active=cuenta.is_active,
    )


@router.patch("/{account_id}", dependencies=[Depends(require_permission("acct", "editar"))])
async def actualizar(
    account_id: int,
    data: CuentaUpdate,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if data.name is None and data.is_active is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="al menos un campo (name o is_active) es requerido",
        )

    try:
        cuenta = await actualizar_cuenta(db, empresa_id, account_id, name=data.name, is_active=data.is_active)
    except AccountError as e:
        if e.code == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        if e.code == "name_duplicate":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        if e.code == "account_has_entries":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CuentaResponse(
        id=cuenta.id,
        code=cuenta.code,
        name=cuenta.name,
        level=cuenta.level,
        is_selectable=cuenta.is_selectable,
        is_active=cuenta.is_active,
    )


@router.get("/{account_id}", dependencies=[Depends(require_permission("acct", "ver"))])
async def detalle(
    account_id: int,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    cuenta = await obtener_cuenta(db, empresa_id, account_id)
    if cuenta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta inexistente en la empresa activa",
        )
    return CuentaResponse(
        id=cuenta.id,
        code=cuenta.code,
        name=cuenta.name,
        level=cuenta.level,
        is_selectable=cuenta.is_selectable,
        is_active=cuenta.is_active,
    )