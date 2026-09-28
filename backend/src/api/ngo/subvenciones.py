"""Endpoints de subvenciones e imputación de gastos (SPEC-019 US1).

Registro, listado, detalle, edición y transición de estado de subvenciones, más
la imputación/desimputación de gastos a nivel de línea del diario y el informe
de justificación con exportación CSV/JSON. La empresa activa SIEMPRE la deriva
la sesión (constitución III); guard por operación del catálogo SPEC-015.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.ngo.deps import get_empresa_activa, require_permission
from database import get_db
from services.ngo.errores import NgoError
from services.ngo.justificacion import (
    desimputar_gasto,
    exportar_informe,
    imputar_gasto,
    informe_justificacion,
)
from services.ngo.subvenciones import (
    cambiar_estado_subvencion,
    crear_subvencion,
    editar_subvencion,
    listar_subvenciones,
    obtener_subvencion,
)

router = APIRouter(prefix="/api/v1", tags=["subvenciones"])

Db = Annotated[AsyncSession, Depends(get_db)]


class SubvencionCreate(BaseModel):
    entidad_concedente: str = Field(..., min_length=1, max_length=120)
    programa: str = Field(..., min_length=1, max_length=120)
    referencia: str | None = Field(None, max_length=40)
    importe_concedido: Decimal
    ejercicio: int = Field(..., ge=2000, le=2100)
    partidas: list[str] | None = None
    observaciones: str | None = None


class SubvencionPatch(BaseModel):
    entidad_concedente: str | None = Field(None, min_length=1, max_length=120)
    programa: str | None = Field(None, min_length=1, max_length=120)
    referencia: str | None = Field(None, max_length=40)
    observaciones: str | None = None
    partidas: list[str] | None = None


class SubvencionEstado(BaseModel):
    estado: str = Field(..., min_length=1, max_length=20)
    asiento_rectificativo_id: uuid.UUID | None = None


class GastoImputar(BaseModel):
    asiento_id: uuid.UUID
    linea_id: uuid.UUID
    importe_asignado: Decimal
    partida: str | None = Field(None, max_length=80)


def _manejar(exc: NgoError) -> HTTPException:
    if exc.code in (
        "subvencion_no_encontrada",
        "asiento_no_encontrado",
        "linea_no_encontrada",
        "gasto_no_encontrado",
    ):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in (
        "referencia_duplicada",
        "transicion_no_permitida",
        "falta_rectificativo",
        "excede_disponible",
        "excede_importe_linea",
        "gasto_ya_imputado",
        "gasto_ya_usado",
        "subvencion_cerrada",
        "linea_no_pertenece_asiento",
        "linea_no_es_gasto",
        "asiento_no_asentado",
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.post(
    "/subvenciones",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ngo", "crear"))],
)
async def crear_subvencion_ep(
    body: SubvencionCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await crear_subvencion(
            db,
            empresa_id=empresa_id,
            entidad_concedente=body.entidad_concedente,
            programa=body.programa,
            referencia=body.referencia,
            importe_concedido=body.importe_concedido,
            ejercicio=body.ejercicio,
            partidas=body.partidas,
            observaciones=body.observaciones,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.get("/subvenciones", dependencies=[Depends(require_permission("ngo", "ver"))])
async def listar_subvenciones_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    estado: Annotated[str | None, Query(max_length=20)] = None,
    ejercicio: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await listar_subvenciones(
            db,
            empresa_id=empresa_id,
            estado=estado,
            ejercicio=ejercicio,
            page=page,
            page_size=page_size,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.get(
    "/subvenciones/{subvencion_id}",
    dependencies=[Depends(require_permission("ngo", "ver"))],
)
async def detalle_subvencion_ep(
    subvencion_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    dto = await obtener_subvencion(db, empresa_id=empresa_id, subvencion_id=subvencion_id)
    if dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La subvención no existe o pertenece a otra empresa",
        )
    return dto


@router.patch(
    "/subvenciones/{subvencion_id}",
    dependencies=[Depends(require_permission("ngo", "editar"))],
)
async def editar_subvencion_ep(
    subvencion_id: uuid.UUID,
    body: SubvencionPatch,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await editar_subvencion(
            db,
            empresa_id=empresa_id,
            subvencion_id=subvencion_id,
            entidad_concedente=body.entidad_concedente,
            programa=body.programa,
            referencia=body.referencia,
            observaciones=body.observaciones,
            partidas=body.partidas,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/subvenciones/{subvencion_id}/estado",
    dependencies=[Depends(require_permission("ngo", "aprobar"))],
)
async def estado_subvencion_ep(
    subvencion_id: uuid.UUID,
    body: SubvencionEstado,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await cambiar_estado_subvencion(
            db,
            empresa_id=empresa_id,
            subvencion_id=subvencion_id,
            estado=body.estado,
            asiento_rectificativo_id=body.asiento_rectificativo_id,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.post(
    "/subvenciones/{subvencion_id}/gastos",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ngo", "crear"))],
)
async def imputar_gasto_ep(
    subvencion_id: uuid.UUID,
    body: GastoImputar,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await imputar_gasto(
            db,
            empresa_id=empresa_id,
            subvencion_id=subvencion_id,
            asiento_id=body.asiento_id,
            linea_id=body.linea_id,
            importe_asignado=body.importe_asignado,
            partida=body.partida,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.delete(
    "/subvenciones/{subvencion_id}/gastos/{gasto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("ngo", "baja"))],
)
async def desimputar_gasto_ep(
    subvencion_id: uuid.UUID,
    gasto_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> Response:
    try:
        await desimputar_gasto(
            db,
            empresa_id=empresa_id,
            subvencion_id=subvencion_id,
            gasto_id=gasto_id,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/informes/subvenciones/{subvencion_id}/justificacion",
    dependencies=[Depends(require_permission("ngo", "ver"))],
)
async def informe_justificacion_ep(
    subvencion_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    informe = await informe_justificacion(db, empresa_id=empresa_id, subvencion_id=subvencion_id)
    if informe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La subvención no existe o pertenece a otra empresa",
        )
    return informe


@router.get(
    "/informes/subvenciones/{subvencion_id}/justificacion/exportar",
    dependencies=[Depends(require_permission("ngo", "ver"))],
)
async def exportar_informe_ep(
    subvencion_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    formato: Annotated[str, Query(max_length=5)] = "csv",
) -> Response:
    try:
        content, content_type, filename = await exportar_informe(
            db,
            empresa_id=empresa_id,
            subvencion_id=subvencion_id,
            formato=formato,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )