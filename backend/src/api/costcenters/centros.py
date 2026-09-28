"""Endpoints de centros de coste (SPEC-017 US1).

Alta, listado paginado, árbol con closure resuelta, detalle, edición e
inactivación/reactivación (nunca borrado físico: FR-005). La empresa activa
SIEMPRE la deriva la sesión (`get_empresa_activa`), nunca el body/ruta
(constitución III). Guard por operación del catálogo SPEC-015 (modulo
"centros"). Ver `contracts/api-contracts.md`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.costcenters.deps import get_empresa_activa, require_permission
from database import get_db
from services.costcenters.centros import (
    arbol_centros,
    crear_centro,
    editar_centro,
    inactivar_centro,
    listar_centros,
    obtener_centro,
    reactivar_centro,
)
from services.costcenters.errores import CostcenterError

router = APIRouter(prefix="/api/v1/centros", tags=["centros"])

Db = Annotated[AsyncSession, Depends(get_db)]


class CentroCreate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20)
    nombre: str = Field(..., min_length=1, max_length=120)
    tipo: str = Field(..., min_length=1, max_length=20)
    parent_id: uuid.UUID | None = None
    subvencion_id: uuid.UUID | None = None


class CentroPatch(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=120)
    tipo: str | None = Field(None, min_length=1, max_length=20)
    parent_id: uuid.UUID | None = None
    subvencion_id: uuid.UUID | None = None


def _manejar(exc: CostcenterError) -> HTTPException:
    if exc.code in ("centro_no_encontrado", "parent_no_encontrado"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in ("codigo_duplicado", "ciclo", "estado_duplicado"):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("centros", "crear"))],
)
async def crear_centro_ep(
    body: CentroCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await crear_centro(
            db,
            empresa_id=empresa_id,
            codigo=body.codigo,
            nombre=body.nombre,
            tipo=body.tipo,
            parent_id=body.parent_id,
            subvencion_id=body.subvencion_id,
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.get("", dependencies=[Depends(require_permission("centros", "ver"))])
async def listar_centros_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    estado: Annotated[str | None, Query(max_length=20)] = None,
    tipo: Annotated[str | None, Query(max_length=20)] = None,
    padre_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await listar_centros(
            db,
            empresa_id=empresa_id,
            estado=estado,
            tipo=tipo,
            padre_id=padre_id,
            page=page,
            page_size=page_size,
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.get("/arbol", dependencies=[Depends(require_permission("centros", "ver"))])
async def arbol_centros_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    return await arbol_centros(db, empresa_id=empresa_id)


@router.get(
    "/{centro_id}",
    dependencies=[Depends(require_permission("centros", "ver"))],
)
async def detalle_centro_ep(
    centro_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        dto = await obtener_centro(db, empresa_id=empresa_id, centro_id=centro_id)
    except CostcenterError as exc:
        raise _manejar(exc) from exc
    if dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El centro no existe o pertenece a otra empresa",
        )
    return dto


@router.patch(
    "/{centro_id}",
    dependencies=[Depends(require_permission("centros", "editar"))],
)
async def editar_centro_ep(
    centro_id: uuid.UUID,
    body: CentroPatch,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await editar_centro(
            db,
            empresa_id=empresa_id,
            centro_id=centro_id,
            nombre=body.nombre,
            tipo=body.tipo,
            parent_id=body.parent_id,
            subvencion_id=body.subvencion_id,
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/{centro_id}/inactivar",
    dependencies=[Depends(require_permission("centros", "baja"))],
)
async def inactivar_centro_ep(
    centro_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await inactivar_centro(db, empresa_id=empresa_id, centro_id=centro_id)
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/{centro_id}/reactivar",
    dependencies=[Depends(require_permission("centros", "editar"))],
)
async def reactivar_centro_ep(
    centro_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await reactivar_centro(db, empresa_id=empresa_id, centro_id=centro_id)
    except CostcenterError as exc:
        raise _manejar(exc) from exc