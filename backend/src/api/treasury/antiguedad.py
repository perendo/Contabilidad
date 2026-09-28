"""Informe de antigüedad de saldos (SPEC-011 US3)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from services.treasury.antiguedad import calcular_antiguedad

router = APIRouter(prefix="/antiguedad", tags=["antiguedad"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def informe_antiguedad(
    empresa_id: EmpresaDep,
    session: SesionDep,
    fecha_corte: Annotated[date, Query(description="Fecha de corte")],
):
    return await calcular_antiguedad(session, empresa_id=empresa_id, fecha_corte=fecha_corte)
