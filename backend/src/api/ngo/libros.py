"""Endpoints de libros oficiales (SPEC-019 US2 / FR-005).

Generación de PDF de libros (diario/mayor/cuentas_anuales) de un ejercicio
cerrado, listado y descarga. La empresa activa SIEMPRE la deriva la sesión
(constitución III); guard por operación del catálogo SPEC-015.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.ngo.deps import get_empresa_activa, require_permission
from database import get_db
from services.ngo.errores import NgoError
from services.ngo.libros_pdf import generar_libros, listar_libros, obtener_libro

router = APIRouter(prefix="/api/v1/libros", tags=["libros"])

Db = Annotated[AsyncSession, Depends(get_db)]


class LibrosGenerar(BaseModel):
    tipos: list[str]


def _manejar(exc: NgoError) -> HTTPException:
    if exc.code == "ejercicio_inexistente":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code == "ejercicio_abierto":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.post(
    "/{ejercicio}/generar",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ngo", "crear"))],
)
async def generar_libros_ep(
    ejercicio: int,
    body: LibrosGenerar,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> dict:
    try:
        libros = await generar_libros(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            tipos=body.tipos,
        )
    except NgoError as exc:
        raise _manejar(exc) from exc
    return {"items": libros}


@router.get("/{ejercicio}", dependencies=[Depends(require_permission("ngo", "ver"))])
async def listar_libros_ep(
    ejercicio: int,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return await listar_libros(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{libro_id}/descarga",
    dependencies=[Depends(require_permission("ngo", "ver"))],
)
async def descargar_libro_ep(
    libro_id: uuid.UUID,
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
) -> Response:
    libro = await obtener_libro(db, empresa_id=empresa_id, libro_id=libro_id)
    if libro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El libro no existe o pertenece a otra empresa",
        )
    return Response(
        content=libro.contenido_pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="libro_{libro.tipo.value}_{libro.ejercicio}.pdf"'
        },
    )