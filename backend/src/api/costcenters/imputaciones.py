"""Endpoints de imputación por línea (SPEC-017 US2).

Imputar/quitar/quitar imputación sobre líneas de borrador; las líneas de
asientos POSTED/CANCELLED responden 409 (constitución II: rectificación vía
motor, nunca edición). La empresa activa la deriva la sesión; los guard son
de modulo "centros" (SPEC-015). Contrato: `contracts/api-contracts.md`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.costcenters.deps import get_empresa_activa, require_permission
from database import get_db
from services.costcenters.errores import CostcenterError
from services.costcenters.imputacion import (
    imputar_linea,
    listar_imputaciones,
    quitar_imputacion,
    rectificar_imputacion,
)

router = APIRouter(prefix="/api/v1", tags=["imputaciones"])

Db = Annotated[AsyncSession, Depends(get_db)]


class ImputacionCreate(BaseModel):
    centro_coste_id: uuid.UUID


def _manejar(exc: CostcenterError) -> HTTPException:
    if exc.code in (
        "centro_no_encontrado",
        "asiento_no_encontrado",
        "linea_no_encontrada",
        "centro_otra_empresa",
    ):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in ("linea_posteada", "estado_invalido", "imputacion_no_existente"):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    if exc.code == "centro_inactivo":
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.post(
    "/asientos/{asiento_id}/lineas/{linea_id}/imputar",
    dependencies=[Depends(require_permission("centros", "editar"))],
)
async def imputar_linea_ep(
    asiento_id: uuid.UUID,
    linea_id: uuid.UUID,
    body: ImputacionCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await imputar_linea(
            db,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            linea_id=linea_id,
            centro_coste_id=body.centro_coste_id,
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.delete(
    "/asientos/{asiento_id}/lineas/{linea_id}/imputar",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("centros", "editar"))],
)
async def quitar_imputacion_ep(
    asiento_id: uuid.UUID,
    linea_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> None:
    try:
        await quitar_imputacion(
            db, empresa_id=empresa_id, asiento_id=asiento_id, linea_id=linea_id
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/asientos/{asiento_id}/lineas/{linea_id}/rectificar-imputacion",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("centros", "editar"))],
)
async def rectificar_imputacion_ep(
    asiento_id: uuid.UUID,
    linea_id: uuid.UUID,
    body: ImputacionCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    """Reasigna una imputación POSTED creando un asiento ADJUSTMENT (motor)."""
    try:
        return await rectificar_imputacion(
            db,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            linea_id=linea_id,
            centro_coste_id=body.centro_coste_id,
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.get(
    "/imputaciones",
    dependencies=[Depends(require_permission("centros", "ver"))],
)
async def listar_imputaciones_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    asiento_id: uuid.UUID | None = None,
    centro_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await listar_imputaciones(
            db,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            centro_id=centro_id,
            page=page,
            page_size=page_size,
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc