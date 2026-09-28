"""Endpoints de legalización de libros oficiales (SPEC-019 US2 / FR-006).

Emisión del fichero de legalización (ejercicio cerrado, huella de integridad),
listado y descarga. La empresa activa SIEMPRE la deriva la sesión (constitución
III); guard por operación del catálogo SPEC-015.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.ngo.deps import get_empresa_activa, require_permission
from database import get_db
from services.ngo.errores import NgoError
from services.ngo.legalizacion import (
    emitir_legalizacion,
    listar_legalizaciones,
    obtener_legalizacion,
)

router = APIRouter(prefix="/api/v1/legalizaciones", tags=["legalizaciones"])

Db = Annotated[AsyncSession, Depends(get_db)]


class LegalizacionCreate(BaseModel):
    ejercicio: int
    fecha_legalizacion: date | None = None


def _manejar(exc: NgoError) -> HTTPException:
    if exc.code == "ejercicio_inexistente":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in ("ejercicio_abierto", "huella_no_coincide"):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ngo", "crear"))],
)
async def emitir_legalizacion_ep(
    body: LegalizacionCreate,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        return await emitir_legalizacion(
            db,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            fecha_legalizacion=body.fecha_legalizacion,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc


@router.get("", dependencies=[Depends(require_permission("ngo", "ver"))])
async def listar_legalizaciones_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return await listar_legalizaciones(
        db,
        empresa_id=empresa_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{legalizacion_id}/descarga",
    dependencies=[Depends(require_permission("ngo", "ver"))],
)
async def descargar_legalizacion_ep(
    legalizacion_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> Response:
    legalizacion = await obtener_legalizacion(
        db, empresa_id=empresa_id, legalizacion_id=legalizacion_id
    )
    if legalizacion is None or legalizacion.fichero is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La legalización no existe o pertenece a otra empresa",
        )
    return Response(
        content=legalizacion.fichero,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="legalizacion_{legalizacion.ejercicio}.txt"'
        },
    )