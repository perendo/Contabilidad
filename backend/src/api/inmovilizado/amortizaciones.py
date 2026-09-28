"""Endpoints de amortizaciones generadas (SPEC-014).

Generación por período (200), listado con filtros y reapertura de un
período ya amortizado (200, REVERSAL con trazabilidad; constitución II).
La empresa activa proviene de la sesión (constitución III).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.inmovilizado.deps import get_empresa_id
from database import get_db
from services.inmovilizado import generacion as generacion_svc
from services.inmovilizado.errores import InmovilizadoError

router = APIRouter(prefix="/amortizaciones", tags=["inmovilizado"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


def _http(exc: InmovilizadoError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": exc.message},
    )


class GenerarBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    periodo: int = Field(ge=1, le=12)


class ReabrirBody(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


@router.post("/generar", dependencies=[Depends(require_permission("inmovilizado", "crear"))])
async def generar(body: GenerarBody, empresa_id: EmpresaDep, session: SessionDep) -> dict[str, Any]:
    try:
        resultado = await generacion_svc.generar_amortizacion(
            session,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            periodo=body.periodo,
            actor="api",
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc
    resultado["generados"] = resultado.pop("generadas", [])
    resultado["n"] = len(resultado["generados"])
    return resultado


@router.get("", dependencies=[Depends(require_permission("inmovilizado", "ver"))])
async def listar_amortizaciones(
    empresa_id: EmpresaDep,
    session: SessionDep,
    activo_id: uuid.UUID | None = None,
    ejercicio: int | None = None,
    periodo: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=40, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return await generacion_svc.listar_amortizaciones(
            session,
            empresa_id=empresa_id,
            activo_id=activo_id,
            ejercicio=ejercicio,
            periodo=periodo,
            page=page,
            page_size=page_size,
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc


@router.get("/activos/{activo_id}", dependencies=[Depends(require_permission("inmovilizado", "ver"))])
async def listar_amortizaciones_activo(
    activo_id: uuid.UUID, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        return await generacion_svc.listar_amortizaciones(
            session,
            empresa_id=empresa_id,
            activo_id=activo_id,
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc


@router.post("/{amortizacion_id}/reabrir", dependencies=[Depends(require_permission("inmovilizado", "editar"))])
async def reabrir(
    amortizacion_id: uuid.UUID,
    body: ReabrirBody,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        resultado = await generacion_svc.reabrir_amortizacion(
            session,
            empresa_id=empresa_id,
            amortizacion_id=amortizacion_id,
            actor="api",
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc
    resultado["reversal_asiento_id"] = resultado.pop("asiento_reapertura_id")
    resultado["estado"] = "pendiente"
    return resultado


__all__ = ["router"]