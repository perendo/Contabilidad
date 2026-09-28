"""Endpoints de la interfaz SII (SPEC-012, sin envio)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from api.fiscal.comun import http_error
from database import get_db
from services.vat.errores import VatError
from services.vat.sii import (
    configurar_sii,
    generar_xml_sii,
    obtener_configuracion_sii,
)

router = APIRouter(prefix="/api/v1/sii", tags=["fiscal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


@router.get("/configuracion", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def obtener_configuracion(
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    config = await obtener_configuracion_sii(session, empresa_id)
    return {
        "habilitado": config.habilitado,
        "obligatorio": config.obligatorio,
        "identificador_emisor": config.identificador_emisor,
        "periodicidad_303": "MES" if config.habilitado else "TRIMESTRE",
    }


class SiiConfigRequest(BaseModel):
    habilitado: bool
    identificador_emisor: str | None = Field(None, max_length=20)
    obligatorio: bool | None = None


@router.post("/configuracion", dependencies=[Depends(require_permission("fiscal", "configurar"))])
async def actualizar_configuracion(
    body: SiiConfigRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        return await configurar_sii(
            session,
            empresa_id=empresa_id,
            habilitado=body.habilitado,
            identificador_emisor=body.identificador_emisor,
            obligatorio=body.obligatorio,
        )
    except VatError as exc:
        raise http_error(exc) from exc


@router.get("/operaciones/{tipo}", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def operaciones(
    tipo: str,
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int, Query()],
    periodo: Annotated[int, Query()],
    tipo_periodo: Annotated[str, Query()] = "TRIMESTRE",
) -> dict:
    try:
        return await generar_xml_sii(
            session,
            empresa_id=empresa_id,
            tipo=tipo,
            ejercicio=ejercicio,
            periodo=periodo,
            tipo_periodo=tipo_periodo,
        )
    except VatError as exc:
        raise http_error(exc) from exc