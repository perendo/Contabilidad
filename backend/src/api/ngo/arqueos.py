"""Endpoints de arqueos (SPEC-019 US3 / FR-009).

Realización de arqueos (saldo en libros vs efectivo contado), aprobación con
asiento de ajuste que cuadra la 570, archivado (diferencia pendiente visible) y
listado. La empresa activa SIEMPRE la deriva la sesión (constitución III); guard
por operación del catálogo SPEC-015.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.ngo.deps import get_empresa_activa, require_permission
from database import get_db
from services.ngo.arqueo import (
    aprobar_arqueo,
    archivar_arqueo,
    listar_arqueos,
    realizar_arqueo,
)
from services.ngo.errores import NgoError

router = APIRouter(prefix="/api/v1", tags=["arqueos"])

Db = Annotated[AsyncSession, Depends(get_db)]


class ArqueoCreate(BaseModel):
    fecha: date
    efectivo_contado: Decimal
    detalle: str | None = None


class AprobarArqueo(BaseModel):
    asiento_ajuste_id: uuid.UUID | None = None


def _manejar(exc: NgoError) -> HTTPException:
    if exc.code in ("arqueo_no_encontrado", "asiento_no_encontrado", "caja_no_encontrada"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in (
        "arqueo_ya_decidido",
        "falta_asiento_ajuste",
        "ajuste_no_cuadra",
        "ajuste_no_asentado",
        "caja_inactiva",
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.post(
    "/cajas/{caja_id}/arqueos",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ngo", "crear"))],
)
async def realizar_arqueo_ep(
    caja_id: uuid.UUID,
    body: ArqueoCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await realizar_arqueo(
            db,
            empresa_id=empresa_id,
            caja_id=caja_id,
            fecha=body.fecha,
            efectivo_contado=body.efectivo_contado,
            detalle=body.detalle,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/arqueos/{arqueo_id}/aprobar",
    dependencies=[Depends(require_permission("ngo", "aprobar"))],
)
async def aprobar_arqueo_ep(
    arqueo_id: uuid.UUID,
    body: AprobarArqueo,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await aprobar_arqueo(
            db,
            empresa_id=empresa_id,
            arqueo_id=arqueo_id,
            asiento_ajuste_id=body.asiento_ajuste_id,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/arqueos/{arqueo_id}/archivar",
    dependencies=[Depends(require_permission("ngo", "editar"))],
)
async def archivar_arqueo_ep(
    arqueo_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await archivar_arqueo(db, empresa_id=empresa_id, arqueo_id=arqueo_id)
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.get("/arqueos", dependencies=[Depends(require_permission("ngo", "ver"))])
async def listar_arqueos_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    caja_id: uuid.UUID | None = None,
    estado: Annotated[str | None, Query(max_length=20)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await listar_arqueos(
            db,
            empresa_id=empresa_id,
            caja_id=caja_id,
            estado=estado,
            page=page,
            page_size=page_size,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc