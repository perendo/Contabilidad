"""Endpoints de modelos fiscales 303/347/349 (SPEC-012 US2/US3)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from api.fiscal.comun import http_error
from database import get_db
from services.vat.errores import VatError
from services.vat.modelos import LIMITE_347, calcular_303, preparar_347, preparar_349

router = APIRouter(prefix="/api/v1/modelos", tags=["fiscal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


@router.get("/303", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def modelo_303(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int, Query()],
    periodo: Annotated[int, Query()],
    tipo_periodo: Annotated[str, Query()] = "TRIMESTRE",
) -> dict:
    try:
        return await calcular_303(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            tipo_periodo=tipo_periodo,
            periodo=periodo,
        )
    except VatError as exc:
        raise http_error(exc) from exc


@router.get("/347", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def modelo_347(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int, Query()],
    limite_incluir: Annotated[Decimal, Query()] = LIMITE_347,
) -> dict:
    return await preparar_347(
        session, empresa_id=empresa_id, ejercicio=ejercicio, limite=limite_incluir
    )


@router.get("/349", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def modelo_349(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int, Query()],
    periodo: Annotated[int, Query()],
    tipo_periodo: Annotated[str, Query()] = "TRIMESTRE",
) -> dict:
    try:
        return await preparar_349(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            tipo_periodo=tipo_periodo,
            periodo=periodo,
        )
    except VatError as exc:
        raise http_error(exc) from exc