"""Cobros por medio (TPV/tarjeta/transferencia) API (SPEC-021 US2)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from models.iam.user import User
from models.treasury.cobro_medio import MedioCobro
from models.treasury.comision import TipoComision
from services.treasury.cobro_medio import (
    CobroMedioError,
    detalle_cobro_medio,
    listar_cobros_medio,
    registrar_cobro_medio,
)
from services.treasury.common import CUENTA_BANCO

router = APIRouter(prefix="/cobros-medio", tags=["cobros-medio"])

SesionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class CobroMedioBody(BaseModel):
    vencimiento_id: uuid.UUID
    medio_cobro: MedioCobro
    fecha_cobro: date
    cuenta_banco: str = CUENTA_BANCO
    importe_comision: str = "0"
    tipo_comision: TipoComision | str = "OTRA"
    banco_codigo: str | None = None
    porcentaje: str | None = None


def _http(exc: CobroMedioError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": str(exc)},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def crear_cobro_medio(
    body: CobroMedioBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        cobro, comisiones = await registrar_cobro_medio(
            session,
            empresa_id=empresa_id,
            vencimiento_id=body.vencimiento_id,
            medio_cobro=body.medio_cobro,
            fecha_cobro=body.fecha_cobro,
            cuenta_banco=body.cuenta_banco or CUENTA_BANCO,
            importe_comision=body.importe_comision,
            tipo_comision=body.tipo_comision,
            banco_codigo=body.banco_codigo,
            porcentaje=body.porcentaje,
            actor=user.full_name,
        )
    except CobroMedioError as exc:
        _http(exc)
    return {
        "id": str(cobro.id),
        "medio_cobro": cobro.medio_cobro.value,
        "importe_total": f"{cobro.importe_total:0.4f}",
        "importe_comision": f"{cobro.importe_comision:0.4f}",
        "importe_neto": f"{cobro.importe_neto:0.4f}",
        "asiento_cobro_id": str(cobro.asiento_cobro_id),
        "comision_id": str(comisiones[0].id) if comisiones else None,
    }


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_cobros(
    empresa_id: EmpresaDep,
    session: SesionDep,
    medio_cobro: Annotated[MedioCobro | None, Query()] = None,
    fecha_desde: Annotated[date | None, Query()] = None,
    fecha_hasta: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = await listar_cobros_medio(
        session,
        empresa_id=empresa_id,
        medio_cobro=medio_cobro,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": items}


@router.get("/{cobro_medio_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_cobro(
    cobro_medio_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SesionDep,
) -> dict[str, Any]:
    datos = await detalle_cobro_medio(
        session, empresa_id=empresa_id, cobro_medio_id=cobro_medio_id
    )
    if datos is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cobro_medio_no_encontrado", "detail": "Cobro inexistente"},
        )
    return datos