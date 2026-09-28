"""Cartera de efectos API (SPEC-021 US1/US3)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from models.iam.user import User
from models.treasury.efecto import EstadoEfecto, TipoEfecto
from services.treasury import cartera
from services.treasury.common import CUENTA_BANCO
from services.treasury.efecto import (
    EfectoError,
    cobrar_efecto,
    impagar_efecto,
    registrar_efecto,
)

router = APIRouter(prefix="/efectos", tags=["efectos"])

SesionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class EfectoBody(BaseModel):
    tercero_id: uuid.UUID
    tipo_efecto: TipoEfecto
    numero_documento: str = Field(min_length=1, max_length=50)
    fecha_emision: date
    fecha_vencimiento: date
    importe: str = Field(pattern=r"^\d+(\.\d{1,4})?$")
    moneda: str = "EUR"
    notas: str | None = None


class CobrarBody(BaseModel):
    fecha_cobro: date
    cuenta_banco: str = CUENTA_BANCO


class ImpagoBody(BaseModel):
    fecha_impago: date
    motivo: str | None = None
    gastos_devolucion: str = "0"
    cuenta_banco: str = CUENTA_BANCO


def _http(exc: EfectoError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": str(exc)},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def crear_efecto(
    body: EfectoBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        efecto = await registrar_efecto(
            session,
            empresa_id=empresa_id,
            tercero_id=body.tercero_id,
            tipo_efecto=body.tipo_efecto,
            numero_documento=body.numero_documento,
            fecha_emision=body.fecha_emision,
            fecha_vencimiento=body.fecha_vencimiento,
            importe=body.importe,
            moneda=body.moneda,
            notas=body.notas,
            actor=user.full_name,
        )
    except EfectoError as exc:
        _http(exc)
    return {
        "id": str(efecto.id),
        "estado": efecto.estado.value,
    }


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_efectos(
    empresa_id: EmpresaDep,
    session: SesionDep,
    estado: Annotated[EstadoEfecto | None, Query()] = None,
    tipo_efecto: Annotated[TipoEfecto | None, Query()] = None,
    tercero_id: Annotated[uuid.UUID | None, Query()] = None,
    fecha_desde: Annotated[date | None, Query()] = None,
    fecha_hasta: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = await cartera.consultar_cartera(
        session,
        empresa_id=empresa_id,
        estado=estado,
        tipo_efecto=tipo_efecto,
        tercero_id=tercero_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        limit=limit,
        offset=offset,
    )
    agrupado = await cartera.agrupar_cartera(
        session,
        empresa_id=empresa_id,
        estado=estado,
        tipo_efecto=tipo_efecto,
        tercero_id=tercero_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    return {"total": total, "items": items, **agrupado}


@router.get("/{efecto_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_efecto(
    efecto_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SesionDep,
) -> dict[str, Any]:
    datos = await cartera.detalle_efecto(
        session, empresa_id=empresa_id, efecto_id=efecto_id
    )
    if datos is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "efecto_no_encontrado", "detail": "Efecto inexistente"},
        )
    return datos


@router.post(
    "/{efecto_id}/cobrar",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def cobrar_efecto_endpoint(
    efecto_id: uuid.UUID,
    body: CobrarBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        efecto = await cobrar_efecto(
            session,
            empresa_id=empresa_id,
            efecto_id=efecto_id,
            fecha_cobro=body.fecha_cobro,
            cuenta_banco=body.cuenta_banco or CUENTA_BANCO,
            actor=user.full_name,
        )
    except EfectoError as exc:
        _http(exc)
    return {
        "id": str(efecto.id),
        "estado": efecto.estado.value,
        "asiento_cobro_id": str(efecto.asiento_cobro_id),
    }


@router.post(
    "/{efecto_id}/impago",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def impago_efecto_endpoint(
    efecto_id: uuid.UUID,
    body: ImpagoBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        efecto = await impagar_efecto(
            session,
            empresa_id=empresa_id,
            efecto_id=efecto_id,
            fecha_impago=body.fecha_impago,
            motivo=body.motivo,
            gastos_devolucion=body.gastos_devolucion,
            cuenta_banco=body.cuenta_banco or CUENTA_BANCO,
            actor=user.full_name,
        )
    except EfectoError as exc:
        _http(exc)
    return {
        "id": str(efecto.id),
        "estado": efecto.estado.value,
        "asiento_impago_id": str(efecto.asiento_impago_id),
    }