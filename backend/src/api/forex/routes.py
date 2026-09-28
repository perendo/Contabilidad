"""Rutas del módulo forex (SPEC-016): divisas, tipos de cambio, asientos en
divisa y valoración a cierre. Endpoints versionados bajo ``/api/v1`` con la
empresa activa derivada de la cabecera de sesión y guard por operación del
catálogo SPEC-015 (modulo "divisas").
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.forex.deps import get_empresa_id, require_permission
from database import get_db
from services.forex.asiento_divisa import (
    detalle_asiento_divisa,
    registrar_asiento_divisa,
)
from services.forex.errores import ForexError
from services.forex.monedas import listar_divisas, registrar_divisa
from services.forex.tipos import (
    corregir_tipo,
    historial_tipos,
    listar_tipos,
    obtener_historial_asiento,
    registrar_tipo,
)
from services.forex.valoracion import iniciar_valoracion, listar_diferencias

router = APIRouter(
    prefix="/api/v1",
    tags=["forex"],
    dependencies=[Depends(get_empresa_id)],
)

Db = Annotated[AsyncSession, Depends(get_db)]


class DivisaCreate(BaseModel):
    codigo_iso: str = Field(min_length=3, max_length=3)
    activa: bool = True


class TipoCambioCreate(BaseModel):
    divisa_id: uuid.UUID
    fecha: date
    ratio: str


class TipoCambioPatch(BaseModel):
    ratio: str
    motivo: str


class LineaDivisaInput(BaseModel):
    cuenta_id: int
    debe_divisa: str = "0.0000"
    haber_divisa: str = "0.0000"


class RatioExplicito(BaseModel):
    ratio: str
    fecha_valor: date | None = None


class AsientoDivisaCreate(BaseModel):
    fecha: date
    divisa_id: uuid.UUID
    concepto: str | None = None
    lineas: list[LineaDivisaInput]
    tipo_cambio_id: uuid.UUID | None = None
    tipo_ratio_explicito: RatioExplicito | None = None


class ValoracionCreate(BaseModel):
    ejercicio: int
    fecha_valoracion: date


def _manejar_forex(exc: ForexError) -> HTTPException:
    if exc.code in {
        "tipo_no_encontrado",
        "divisa_no_encontrada",
        "cuenta_no_encontrada",
        "asiento_no_encontrado",
    }:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in {
        "tipo_ya_existe",
        "tipo_sellado_inmutable",
        "divisa_ya_existe",
        "valoracion_ya_existente",
        "ejercicio_cerrado",
    }:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.get("/divisas", dependencies=[Depends(require_permission("divisas", "ver"))])
async def get_divisas(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> dict:
    return await listar_divisas(db, empresa_id)


@router.post(
    "/divisas",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("divisas", "crear"))],
)
async def post_divisas(
    body: DivisaCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> dict:
    try:
        return await registrar_divisa(
            db, empresa_id=empresa_id, codigo_iso=body.codigo_iso, activa=body.activa
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc


@router.post(
    "/tipos-cambio",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("divisas", "crear"))],
)
async def post_tipo_cambio(
    body: TipoCambioCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> dict:
    try:
        return await registrar_tipo(
            db,
            empresa_id=empresa_id,
            divisa_id=body.divisa_id,
            ratio=body.ratio,
            fecha=body.fecha,
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc


@router.patch(
    "/tipos-cambio/{tipo_id}",
    dependencies=[Depends(require_permission("divisas", "editar"))],
)
async def patch_tipo_cambio(
    tipo_id: uuid.UUID,
    body: TipoCambioPatch,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> dict:
    try:
        return await corregir_tipo(
            db,
            empresa_id=empresa_id,
            tipo_id=tipo_id,
            ratio=body.ratio,
            motivo=body.motivo,
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc


@router.get(
    "/tipos-cambio",
    dependencies=[Depends(require_permission("divisas", "ver"))],
)
async def get_tipos_cambio(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    divisa_id: uuid.UUID | None = None,
    fecha_gte: date | None = None,
    fecha_lte: date | None = None,
    sellado: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    try:
        return await listar_tipos(
            db,
            empresa_id=empresa_id,
            divisa_id=divisa_id,
            fecha_gte=fecha_gte,
            fecha_lte=fecha_lte,
            sellado=sellado,
            page=page,
            page_size=page_size,
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc


@router.get(
    "/tipos-cambio/historial",
    dependencies=[Depends(require_permission("divisas", "ver"))],
)
async def get_historial_tipos(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    asiento_id: uuid.UUID | None = None,
    divisa_id: uuid.UUID | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    sellado: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if asiento_id is not None:
        item = await obtener_historial_asiento(db, empresa_id, asiento_id)
        if item is None and divisa_id is None and fecha_desde is None and fecha_hasta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No hay tipo de cambio para el asiento en la empresa activa",
            )
        items = [item] if item is not None else []
        return {
            "items": items,
            "total": len(items),
            "page": page,
            "page_size": page_size,
            "filtrado_por": "asiento_id",
        }
    try:
        return await historial_tipos(
            db,
            empresa_id=empresa_id,
            divisa_id=divisa_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            sellado=sellado,
            page=page,
            page_size=page_size,
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc


@router.post(
    "/asientos-divisa",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("divisas", "crear"))],
)
async def post_asiento_divisa(
    body: AsientoDivisaCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> dict:
    ratio_explicito: str | Decimal | None = None
    if body.tipo_ratio_explicito is not None:
        ratio_explicito = body.tipo_ratio_explicito.ratio
    try:
        return await registrar_asiento_divisa(
            db,
            empresa_id=empresa_id,
            fecha=body.fecha,
            divisa_id=body.divisa_id,
            concepto=body.concepto or "Asiento en divisa",
            lineas=[l.model_dump() for l in body.lineas],
            tipo_cambio_id=body.tipo_cambio_id,
            ratio_explicito=ratio_explicito,
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc


@router.get(
    "/asientos-divisa/{asiento_id}",
    dependencies=[Depends(require_permission("divisas", "ver"))],
)
async def get_asiento_divisa(
    asiento_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> dict:
    detalle = await detalle_asiento_divisa(db, empresa_id, asiento_id)
    if detalle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El asiento no existe o no es un asiento en divisa en la empresa activa",
        )
    return detalle


@router.post(
    "/valoraciones",
    dependencies=[Depends(require_permission("divisas", "editar"))],
)
async def post_valoracion(
    body: ValoracionCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> dict:
    try:
        return await iniciar_valoracion(
            db,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            fecha_valoracion=body.fecha_valoracion,
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc


@router.get(
    "/diferencias-cambio",
    dependencies=[Depends(require_permission("divisas", "ver"))],
)
async def get_diferencias_cambio(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_id)],
    ejercicio: int | None = None,
    divisa_id: uuid.UUID | None = None,
    cuenta_id: int | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    try:
        return await listar_diferencias(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            divisa_id=divisa_id,
            cuenta_id=cuenta_id,
            estado=estado,
            page=page,
            page_size=page_size,
        )
    except ForexError as exc:
        raise _manejar_forex(exc) from exc