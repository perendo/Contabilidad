"""Endpoints de exportacion de modelos fiscales (SPEC-012 US3).

Prefijo `/api/v1/fiscal/exportaciones`, **no** `/api/v1/exportaciones`: ese
prefijo lo reserva la exportacion integral del tenant de SPEC-029 (su contrato
es `specs/029-export-integral/contracts/api-contracts.md`). Son recursos
distintos, luego rutas distintas: sharing el prefijo hacia que las rutas de
SPEC-029 quedaran ocultas tras las de SPEC-012 al registrarse el router fiscal
antes que `api/export.py` en `main.py`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from api.fiscal.comun import http_error
from database import get_db
from models.fiscal.exportacion_modelo import ModeloFiscal
from models.iam.user import User
from services.vat.errores import VatError
from services.vat.exportacion import (
    contenido_descarga,
    listar_exportaciones,
    obtener_exportacion,
    registrar_exportacion,
)

router = APIRouter(prefix="/api/v1/fiscal/exportaciones", tags=["fiscal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]
UserDep = Annotated[User, Depends(get_current_user)]


class ExportacionRequest(BaseModel):
    modelo: str = Field(..., pattern="^(303|347|349)$")
    ejercicio: int
    periodo: int | None = None
    tipo_periodo: str = "TRIMESTRE"
    formato: str = Field("csv", pattern="^(csv|xml|json)$")


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("fiscal", "importar_exportar"))])
async def exportar(
    body: ExportacionRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict:
    try:
        modelo = ModeloFiscal(body.modelo)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "modelo_invalido", "detail": "Modelo no valido"},
        )
    try:
        resultado = await registrar_exportacion(
            session,
            empresa_id=empresa_id,
            modelo=modelo.value,
            ejercicio=body.ejercicio,
            periodo=body.periodo,
            tipo_periodo=body.tipo_periodo,
            formato=body.formato,
            usuario_id=user.email,
        )
    except VatError as exc:
        raise http_error(exc) from exc
    resultado["url_descarga"] = (
        f"/api/v1/fiscal/exportaciones/{resultado['exportacion_id']}/descargar"
    )
    return resultado


@router.get("", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def listar(
    empresa_id: EmpresaDep,
    session: SessionDep,
    modelo: str | None = None,
    ejercicio: int | None = None,
) -> dict:
    return await listar_exportaciones(
        session, empresa_id=empresa_id, modelo=modelo, ejercicio=ejercicio
    )


@router.get("/{exportacion_id}/descargar", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def descargar(
    exportacion_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> Response:
    exportacion = await obtener_exportacion(
        session, empresa_id=empresa_id, exportacion_id=exportacion_id
    )
    if exportacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "exportacion_no_encontrada", "detail": "Exportacion inexistente"},
        )
    contenido, content_type, nombre = contenido_descarga(exportacion)
    return Response(
        content=contenido,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )