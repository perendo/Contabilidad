"""Configuracion de agrupaciones de informes (SPEC-010 T015)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from models.reporting.configuracion import (
    ActividadEfe,
    ConfiguracionInforme,
    InformeTipo,
)

router = APIRouter(tags=["cuentas-anuales"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class AgrupacionConfig(BaseModel):
    agrupacion_codigo: str = Field(..., min_length=1, max_length=20)
    agrupacion_nombre: str = Field(..., min_length=1, max_length=120)
    cuenta_ini: str = Field(..., min_length=1, max_length=20)
    cuenta_fin: str | None = Field(None, max_length=20)
    actividad_efe: str | None = None
    orden: int = 0


class ConfiguracionRequest(BaseModel):
    ejercicio: int
    informe_tipo: str
    agrupaciones: list[AgrupacionConfig] = Field(..., min_length=1)


@router.post("/configuracion", dependencies=[Depends(require_permission("reporting", "configurar"))])
@router.patch("/configuracion", dependencies=[Depends(require_permission("reporting", "configurar"))])
async def configurar(
    body: ConfiguracionRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        informe = InformeTipo(body.informe_tipo)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "informe_tipo_invalido", "detail": "informe_tipo invalido"},
        )

    await session.execute(
        delete(ConfiguracionInforme).where(
            ConfiguracionInforme.empresa_id == empresa_id,
            ConfiguracionInforme.ejercicio == body.ejercicio,
            ConfiguracionInforme.informe_tipo == informe,
        )
    )
    creadas = 0
    for agrupacion in body.agrupaciones:
        actividad = None
        if agrupacion.actividad_efe:
            try:
                actividad = ActividadEfe(agrupacion.actividad_efe)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": "actividad_invalida",
                        "detail": "actividad_efe invalida",
                    },
                )
        session.add(
            ConfiguracionInforme(
                empresa_id=empresa_id,
                ejercicio=body.ejercicio,
                informe_tipo=informe,
                agrupacion_codigo=agrupacion.agrupacion_codigo,
                agrupacion_nombre=agrupacion.agrupacion_nombre,
                cuenta_ini=agrupacion.cuenta_ini,
                cuenta_fin=agrupacion.cuenta_fin,
                actividad_efe=actividad,
                orden=agrupacion.orden,
            )
        )
        creadas += 1
    await session.flush()
    return {"configuraciones_creadas": creadas}