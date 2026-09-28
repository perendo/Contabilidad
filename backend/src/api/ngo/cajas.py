"""Endpoints de cajas y movimientos (SPEC-019 US3 / FR-008).

Alta, listado, detalle (movimientos + saldo), inactivación y registro de
movimientos de caja/caja chica. Los movimientos generan asientos reales del
motor (SPEC-002) sobre la subcuenta 570; la empresa activa SIEMPRE la deriva la
sesión (constitución III); guard por operación del catálogo SPEC-015.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.ngo.deps import get_empresa_activa, require_permission
from database import get_db
from services.ngo.caja import (
    crear_caja,
    inactivar_caja,
    listar_cajas,
    listar_movimientos,
    obtener_caja,
    registrar_movimiento,
)
from services.ngo.errores import NgoError

router = APIRouter(prefix="/api/v1/cajas", tags=["cajas"])

Db = Annotated[AsyncSession, Depends(get_db)]


class CajaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=80)
    cuenta_570_id: int
    tipo: str = Field(..., min_length=1, max_length=20)


class MovimientoCreate(BaseModel):
    tipo: str = Field(..., min_length=1, max_length=20)
    importe: Decimal
    fecha: date
    concepto: str = Field(..., min_length=1, max_length=255)
    contrapartida_cuenta_id: int


def _manejar(exc: NgoError) -> HTTPException:
    if exc.code in ("caja_no_encontrada", "cuenta_570_no_encontrada", "cuenta_no_encontrada"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in (
        "cuenta_570_asignada",
        "nombre_duplicado",
        "caja_inactiva",
        "ejercicio_cerrado",
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ngo", "crear"))],
)
async def crear_caja_ep(
    body: CajaCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await crear_caja(
            db,
            empresa_id=empresa_id,
            nombre=body.nombre,
            cuenta_570_id=body.cuenta_570_id,
            tipo=body.tipo,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.get("", dependencies=[Depends(require_permission("ngo", "ver"))])
async def listar_cajas_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await listar_cajas(
            db,
            empresa_id=empresa_id,
            page=page,
            page_size=page_size,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.get("/{caja_id}", dependencies=[Depends(require_permission("ngo", "ver"))])
async def detalle_caja_ep(
    caja_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    dto = await obtener_caja(
        db,
        empresa_id=empresa_id,
        caja_id=caja_id,
        page=page,
        page_size=page_size,
    )
    if dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La caja no existe o pertenece a otra empresa",
        )
    return dto


@router.get("/{caja_id}/movimientos", dependencies=[Depends(require_permission("ngo", "ver"))])
async def listar_movimientos_ep(
    caja_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await listar_movimientos(
            db,
            empresa_id=empresa_id,
            caja_id=caja_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            page=page,
            page_size=page_size,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/{caja_id}/movimientos",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ngo", "crear"))],
)
async def registrar_movimiento_ep(
    caja_id: uuid.UUID,
    body: MovimientoCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await registrar_movimiento(
            db,
            empresa_id=empresa_id,
            caja_id=caja_id,
            tipo=body.tipo,
            importe=body.importe,
            fecha=body.fecha,
            concepto=body.concepto,
            contrapartida_cuenta_id=body.contrapartida_cuenta_id,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/{caja_id}/inactivar",
    dependencies=[Depends(require_permission("ngo", "baja"))],
)
async def inactivar_caja_ep(
    caja_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await inactivar_caja(db, empresa_id=empresa_id, caja_id=caja_id)
    except NgoError as exc:
        raise _manejar(exc) from exc