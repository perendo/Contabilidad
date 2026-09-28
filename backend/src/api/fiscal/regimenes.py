"""Endpoints de regimenes especiales (SPEC-012 US4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from api.fiscal.comun import http_error
from database import get_db
from services.vat.configuracion_cuentas import (
    habilitar_criterio_caja,
    habilitar_recargo,
)
from services.vat.criterio_caja import (
    estado_criterio_caja,
    sincronizar_con_vencimientos,
)
from services.vat.errores import VatError
from services.vat.recargo_equivalencia import estado_recargo
from services.vat.sii import obtener_configuracion_sii

router = APIRouter(prefix="/api/v1/regimenes", tags=["fiscal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


@router.get("/estado", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def estado(
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    sii = await obtener_configuracion_sii(session, empresa_id)
    return {
        "recargo_equivalencia": await estado_recargo(session, empresa_id),
        "criterio_caja": await estado_criterio_caja(session, empresa_id),
        "sii": {"habilitado": sii.habilitado, "obligatorio": sii.obligatorio},
    }


class RecargoRequest(BaseModel):
    habilitado: bool
    cuenta_recargo: str | None = Field(None, max_length=20)


@router.post("/recargo-equivalencia", dependencies=[Depends(require_permission("fiscal", "configurar"))])
async def configurar_recargo(
    body: RecargoRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    await habilitar_recargo(
        session, empresa_id, body.habilitado, body.cuenta_recargo
    )
    return await estado_recargo(session, empresa_id)


class CajaRequest(BaseModel):
    habilitado: bool


@router.post("/criterio-caja", dependencies=[Depends(require_permission("fiscal", "configurar"))])
async def configurar_criterio_caja(
    body: CajaRequest,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    await habilitar_criterio_caja(session, empresa_id, body.habilitado)
    estado_actual = await estado_criterio_caja(session, empresa_id)
    try:
        sync = await sincronizar_con_vencimientos(session, empresa_id=empresa_id)
    except VatError as exc:
        raise http_error(exc) from exc
    return {**estado_actual, **sync}