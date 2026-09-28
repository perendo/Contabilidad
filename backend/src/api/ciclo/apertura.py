"""Apertura del ejercicio API (SPEC-009).

Sub-router con prefijo ``/ciclo`` montado bajo el router versionado
``/api/v1`` (ver ``api/ciclo/routes.py``). La empresa activa se deriva de la
sesión (JWT + X-Empresa-Activa); nunca se acepta del path/body (constitución III).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.ciclo.deps import get_empresa_id
from api.deps import require_permission
from database import get_db
from services.cycle import apertura as apertura_svc
from services.cycle.validacion_previa import CicloError, estado_apertura

router = APIRouter(prefix="/ciclo", tags=["ciclo"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


def _http(exc: CicloError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": str(exc)},
    )


class AperturaBody(BaseModel):
    ejercicio: int = Field(
        ge=2000,
        le=2100,
        description="Ejercicio de destino (se abre tras el cierre del anterior)",
    )


@router.post("/apertura", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("acct", "crear"))])
async def abrir_ejercicio(
    body: AperturaBody, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        return await apertura_svc.generar_asiento_apertura(
            session,
            empresa_id=empresa_id,
            ejercicio_destino=body.ejercicio,
            actor="api",
        )
    except CicloError as exc:
        raise _http(exc) from exc


@router.get("/apertura/estado", dependencies=[Depends(require_permission("acct", "ver"))])
async def estado(
    ejercicio: int,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    return await estado_apertura(session, empresa_id, ejercicio)


@router.post("/apertura/anular", dependencies=[Depends(require_permission("acct", "baja"))])
async def anular(
    body: AperturaBody, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        return await apertura_svc.anular_apertura(
            session,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            actor="api",
        )
    except CicloError as exc:
        raise _http(exc) from exc


@router.post("/apertura/regenerar", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("acct", "editar"))])
async def regenerar(
    body: AperturaBody, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        return await apertura_svc.regenerar_apertura(
            session,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            actor="api",
        )
    except CicloError as exc:
        raise _http(exc) from exc