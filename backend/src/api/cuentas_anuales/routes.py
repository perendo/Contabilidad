"""Router versionado de cuentas anuales (SPEC-010).

Endpoints bajo ``/api/v1/cuentas-anuales`` con la empresa activa derivada de la
sesion (nunca del cliente): Balance, PyG, EFE, clasificacion EFE y formulacion
oficial (documento inmutable).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.cuentas_anuales.config import router as config_router
from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.iam.user import User
from services.reporting.efe import clasificar_movimiento, generar_efe
from services.reporting.formulacion import (
    anular_formulacion,
    formular,
    generar_balance,
    listar_formulaciones,
)
from services.reporting.pyg import generar_pyg
from services.reporting.saldos import ReportingError

router = APIRouter(prefix="/api/v1/cuentas-anuales", tags=["cuentas-anuales"])
router.include_router(config_router)

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]
UserDep = Annotated[User, Depends(get_current_user)]

_CODIGOS_404 = {"movimiento_no_encontrado"}
_CODIGOS_409 = {
    "ejercicio_no_cerrado",
    "descuadre_cierre",
    "efe_descuadrado",
    "ya_formulada",
    "sin_formulacion",
}


def _http_error(exc: ReportingError) -> HTTPException:
    detalle = {"code": exc.code, "detail": str(exc)}
    if exc.code in _CODIGOS_404:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detalle)
    if exc.code in _CODIGOS_409:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detalle
    )


@router.get("/{ejercicio}/balance", dependencies=[Depends(require_permission("reporting", "ver"))])
async def balance(
    ejercicio: int,
    empresa_id: EmpresaDep,
    session: SessionDep,
    modo: Annotated[str, Query(pattern="^(provisional|oficial)$")] = "provisional",
    comparativo: bool = False,
) -> dict:
    try:
        return await generar_balance(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            modo=modo,
            comparativo=comparativo,
        )
    except ReportingError as exc:
        raise _http_error(exc) from exc


@router.get("/{ejercicio}/pyg", dependencies=[Depends(require_permission("reporting", "ver"))])
async def pyg(
    ejercicio: int,
    empresa_id: EmpresaDep,
    session: SessionDep,
    modo: Annotated[str, Query(pattern="^(provisional|oficial)$")] = "provisional",
) -> dict:
    try:
        return await generar_pyg(
            session, empresa_id=empresa_id, ejercicio=ejercicio, modo=modo
        )
    except ReportingError as exc:
        raise _http_error(exc) from exc


@router.get("/{ejercicio}/efe", dependencies=[Depends(require_permission("reporting", "ver"))])
async def efe(
    ejercicio: int,
    empresa_id: EmpresaDep,
    session: SessionDep,
    modo: Annotated[str, Query(pattern="^(provisional|oficial)$")] = "provisional",
) -> dict:
    try:
        return await generar_efe(
            session, empresa_id=empresa_id, ejercicio=ejercicio, modo=modo
        )
    except ReportingError as exc:
        raise _http_error(exc) from exc


class ClasificacionRequest(BaseModel):
    movimiento_id: uuid.UUID
    actividad: str
    motivo: str | None = Field(None, max_length=255)


@router.patch("/{ejercicio}/efe/clasificacion", dependencies=[Depends(require_permission("reporting", "editar"))])
async def clasificar_efe(
    ejercicio: int,
    body: ClasificacionRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict:
    try:
        return await clasificar_movimiento(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            linea_id=body.movimiento_id,
            actividad=body.actividad,
            motivo=body.motivo,
            actor=user.email,
        )
    except ReportingError as exc:
        raise _http_error(exc) from exc


class FormularRequest(BaseModel):
    observaciones: str | None = Field(None, max_length=255)


@router.post(
    "/{ejercicio}/formular",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("reporting", "configurar"))],
)
async def formular_ep(
    ejercicio: int,
    body: FormularRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict:
    try:
        return await formular(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            usuario_id=user.email,
            observaciones=body.observaciones,
        )
    except ReportingError as exc:
        raise _http_error(exc) from exc


class AnularRequest(BaseModel):
    motivo: str = Field(..., min_length=1, max_length=255)


@router.post("/{ejercicio}/anular-formulacion", dependencies=[Depends(require_permission("reporting", "baja"))])
async def anular_ep(
    ejercicio: int,
    body: AnularRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict:
    try:
        return await anular_formulacion(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            motivo=body.motivo,
            usuario_id=user.email,
        )
    except ReportingError as exc:
        raise _http_error(exc) from exc


@router.get("/{ejercicio}/formulaciones", dependencies=[Depends(require_permission("reporting", "ver"))])
async def formulaciones(
    ejercicio: int,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    return await listar_formulaciones(
        session, empresa_id=empresa_id, ejercicio=ejercicio
    )