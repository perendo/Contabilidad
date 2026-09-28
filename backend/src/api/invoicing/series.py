"""Endpoints de series de facturación (SPEC-007 T041-T043).

POST/GET ``/facturacion/series`` y PATCH ``/facturacion/series/{id}/estado``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from services.invoicing.errores import InvoicingError
from services.invoicing.numeracion import (
    cambiar_estado_serie,
    crear_serie,
    listar_series,
    numero_formateado,
)

router = APIRouter(prefix="/api/v1/facturacion/series", tags=["facturacion"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class SerieCreate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=10)
    nombre: str | None = Field(None, max_length=100)
    prefijo: str | None = Field(None, max_length=10)
    sufijo: str = Field("", max_length=10)


class SerieEstadoUpdate(BaseModel):
    activa: bool


def _http_error(exc: InvoicingError) -> HTTPException:
    if exc.code == "serie_no_encontrada":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "detail": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": exc.code, "detail": str(exc)},
    )


def _serie_payload(serie) -> dict:
    return {
        "id": str(serie.id),
        "codigo": serie.codigo,
        "nombre": serie.nombre,
        "prefijo": serie.prefijo,
        "sufijo": serie.sufijo,
        "siguiente_numero": serie.siguiente_numero,
        "estado": serie.estado.value,
        "correlativo_ejemplo": numero_formateado(serie, 1),
    }


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("invoicing", "crear"))])
async def crear_serie_ep(
    body: SerieCreate,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        serie = await crear_serie(
            session,
            empresa_id=empresa_id,
            codigo=body.codigo,
            nombre=body.nombre or "",
            prefijo=body.prefijo or "",
            sufijo=body.sufijo,
        )
    except InvoicingError as exc:
        raise _http_error(exc) from exc
    return _serie_payload(serie)


@router.get("", dependencies=[Depends(require_permission("invoicing", "ver"))])
async def listar_series_ep(
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> list[dict]:
    series = await listar_series(session, empresa_id=empresa_id)
    return [_serie_payload(s) for s in series]


@router.patch("/{serie_id}/estado", dependencies=[Depends(require_permission("invoicing", "editar"))])
async def cambiar_estado_serie_ep(
    serie_id: uuid.UUID,
    body: SerieEstadoUpdate,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        serie = await cambiar_estado_serie(
            session,
            empresa_id=empresa_id,
            serie_id=serie_id,
            activa=body.activa,
        )
    except InvoicingError as exc:
        raise _http_error(exc) from exc
    return _serie_payload(serie)