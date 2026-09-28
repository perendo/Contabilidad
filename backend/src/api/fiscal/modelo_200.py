from __future__ import annotations

import uuid
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.iam.user import User
from services.fiscal.errores import FiscalISError
from services.fiscal.modelo_200_gen import (
    descargar_modelo_200,
    generar_modelo_200,
    listar_modelos_200,
    payload_modelo_200,
)

router = APIRouter(prefix="/api/v1/fiscal/is/modelo-200", tags=["fiscal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]
UserDep = Annotated[User, Depends(get_current_user)]

CODIGOS_404 = {"calculo_no_encontrado", "modelo_no_encontrado", "empresa_no_encontrada"}
CODIGOS_409 = {
    "calculo_no_contabilizado",
    "modelo_ya_generado",
    "estado_invalido",
}


class GenerarModelo200Body(BaseModel):
    calculo_is_id: uuid.UUID


class Modelo200Response(BaseModel):
    id: str
    calculo_is_id: str
    fecha_generacion: str
    hash_contenido: str


class Modelos200ListaResponse(BaseModel):
    items: list[Modelo200Response]
    total: int


def _ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _http_error(exc: FiscalISError) -> NoReturn:
    codigo = 404 if exc.code in CODIGOS_404 else 409 if exc.code in CODIGOS_409 else 422
    raise HTTPException(
        status_code=codigo,
        detail={"code": exc.code, "detail": str(exc)},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Modelo200Response,
    dependencies=[Depends(require_permission("fiscal", "crear"))],
)
async def generar(
    body: GenerarModelo200Body,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        modelo = await generar_modelo_200(
            session,
            empresa_id=empresa_id,
            calculo_is_id=body.calculo_is_id,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return payload_modelo_200(modelo)


@router.get(
    "",
    response_model=Modelos200ListaResponse,
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def listar(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    modelos, total = await listar_modelos_200(
        session,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        pagina=offset // limit + 1,
        tamano=limit,
    )
    return {
        "items": [payload_modelo_200(modelo) for modelo in modelos],
        "total": total,
    }


@router.get(
    "/{modelo_200_id}",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def descargar(
    modelo_200_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> Response:
    try:
        contenido, content_type, nombre = await descargar_modelo_200(
            session,
            empresa_id=empresa_id,
            modelo_200_id=modelo_200_id,
        )
    except FiscalISError as exc:
        _http_error(exc)
    return Response(
        content=contenido,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
