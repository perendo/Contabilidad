"""Endpoints for tercero amendments: CondicionProntoPago and MandatoSepa (T011)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from models.treasury.condicion_pronto_pago import CondicionProntoPago
from models.treasury.mandato_sepa import MandatoEstado, MandatoSepa
from models.treasury.remesa import TipoAdeudo
from services import tercero_amend
from services.tercero_amend import (
    MandatoEstadoInput,
    TerceroAmendError,
)

router = APIRouter(prefix="/terceros", tags=["terceros-amend"])


class CondicionCreate(BaseModel):
    plazo_dias: int = Field(gt=0)
    porcentaje: Decimal
    vigente: bool = True
    override_factura_id: uuid.UUID | None = None


class CondicionUpdate(BaseModel):
    plazo_dias: int | None = Field(default=None, gt=0)
    porcentaje: Decimal | None = None
    vigente: bool | None = None
    override_factura_id: uuid.UUID | None = None


class MandatoCreate(BaseModel):
    mandato_ref: str = Field(min_length=1, max_length=35)
    fecha_firma: date
    tipo: TipoAdeudo
    estado: MandatoEstadoInput = MandatoEstadoInput.firmado


class MandatoUpdate(BaseModel):
    estado: MandatoEstadoInput | None = None
    fecha_firma: date | None = None


class SalaCondicion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    empresa_id: int
    tercero_id: uuid.UUID
    plazo_dias: int
    porcentaje: Decimal
    vigente: bool
    override_factura_id: uuid.UUID | None


class SalaMandato(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    empresa_id: int
    tercero_id: uuid.UUID
    mandato_ref: str
    fecha_firma: date
    tipo: TipoAdeudo
    estado: MandatoEstado


def _estado_por_defecto(value: MandatoEstadoInput | None) -> MandatoEstado:
    if value is None:
        return MandatoEstado.firmado
    return MandatoEstado(value.value)


def _raise_service(exception: TerceroAmendError) -> NoReturn:
    message = str(exception)
    if "no encontrada" in message or "no encontrado" in message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if "ya existe" in message or "no se puede" in message:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


@router.get("/{tercero_id}/condiciones", response_model=list[SalaCondicion], dependencies=[Depends(require_permission("ar", "ver"))])
async def listar_condiciones(
    tercero_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> list[CondicionProntoPago]:
    return list(
        (
            await session.scalars(
                select(CondicionProntoPago)
                .where(
                    CondicionProntoPago.empresa_id == empresa_id,
                    CondicionProntoPago.tercero_id == tercero_id,
                )
                .order_by(CondicionProntoPago.vigente.desc(), CondicionProntoPago.id)
            )
        ).all()
    )


@router.post("/{tercero_id}/condiciones", response_model=SalaCondicion, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("ar", "crear"))])
async def crear_condicion(
    tercero_id: uuid.UUID,
    payload: CondicionCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> CondicionProntoPago:
    try:
        return await tercero_amend.crear_condicion(
            session,
            empresa_id=empresa_id,
            tercero_id=tercero_id,
            plazo_dias=payload.plazo_dias,
            porcentaje=payload.porcentaje,
            vigente=payload.vigente,
            override_factura_id=payload.override_factura_id,
        )
    except TerceroAmendError as error:
        _raise_service(error)


@router.patch("/condiciones/{condicion_id}", response_model=SalaCondicion, dependencies=[Depends(require_permission("ar", "editar"))])
async def actualizar_condicion(
    condicion_id: uuid.UUID,
    payload: CondicionUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> CondicionProntoPago:
    try:
        return await tercero_amend.actualizar_condicion(
            session,
            empresa_id=empresa_id,
            condicion_id=condicion_id,
            plazo_dias=payload.plazo_dias,
            porcentaje=payload.porcentaje,
            vigente=payload.vigente,
            override_factura_id=payload.override_factura_id,
        )
    except TerceroAmendError as error:
        _raise_service(error)


@router.post("/{tercero_id}/mandatos", response_model=SalaMandato, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("ar", "crear"))])
async def crear_mandato(
    tercero_id: uuid.UUID,
    payload: MandatoCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> MandatoSepa:
    try:
        return await tercero_amend.crear_mandato(
            session,
            empresa_id=empresa_id,
            tercero_id=tercero_id,
            mandato_ref=payload.mandato_ref,
            fecha_firma=payload.fecha_firma,
            tipo=payload.tipo,
            estado=_estado_por_defecto(payload.estado),
        )
    except TerceroAmendError as error:
        _raise_service(error)


@router.patch("/mandatos/{mandato_id}", response_model=SalaMandato, dependencies=[Depends(require_permission("ar", "editar"))])
async def actualizar_mandato(
    mandato_id: uuid.UUID,
    payload: MandatoUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    empresa_id: Annotated[int, Depends(get_empresa_id)],
) -> MandatoSepa:
    try:
        return await tercero_amend.actualizar_mandato(
            session,
            empresa_id=empresa_id,
            mandato_id=mandato_id,
            estado=payload.estado,
            fecha_firma=payload.fecha_firma,
        )
    except TerceroAmendError as error:
        _raise_service(error)