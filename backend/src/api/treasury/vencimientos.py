"""Vencimientos, cobros y pagos API (SPEC-011 US1/US2)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.iam.user import User
from models.treasury.cobro_pago import CobroPago
from services.treasury.cobros_pagos import (
    CobroPagoError,
    registrar_cobro,
    registrar_pago,
)

router = APIRouter(prefix="/vencimientos", tags=["vencimientos"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]


class OperacionBody(BaseModel):
    fecha: date
    importe: str = Field(pattern=r"^\d+(\.\d{1,4})?$")
    cuenta_tesoreria: str | None = None
    cuenta_bancaria_id: uuid.UUID | None = None


def _raise(exc: CobroPagoError) -> NoReturn:
    if exc.code == "vencimiento_no_encontrado":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if exc.code in ("vencimiento_saldado", "vencimiento_remesado", "vencimiento_cedido", "ejercicio_cerrado"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


def _out(v: Vencimiento) -> dict:
    return {
        "id": str(v.id),
        "recibo_num": v.recibo_num,
        "tercero_id": str(v.tercero_id),
        "tipo": v.tipo.value,
        "fecha_vencimiento": v.fecha_vencimiento.isoformat(),
        "importe": f"{v.importe:0.4f}",
        "acumulado": f"{v.acumulado:0.4f}",
        "saldo_pendiente": f"{v.saldo_pendiente:0.4f}",
        "estado": v.estado.value,
    }


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_vencimientos(
    empresa_id: EmpresaDep,
    session: SesionDep,
    estado: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    condiciones = [Vencimiento.empresa_id == empresa_id]
    if estado:
        condiciones.append(Vencimiento.estado == EstadoVencimiento(estado))
    total = await session.scalar(select(func.count(Vencimiento.id)).where(*condiciones))
    filas = (
        await session.scalars(
            select(Vencimiento)
            .where(*condiciones)
            .order_by(Vencimiento.fecha_vencimiento)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {"total": total or 0, "items": [_out(v) for v in filas]}


@router.get("/{vencimiento_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_vencimiento(vencimiento_id: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    v = await session.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id, Vencimiento.id == vencimiento_id
        )
    )
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vencimiento inexistente")
    return _out(v)


@router.get("/{vencimiento_id}/cobros", dependencies=[Depends(require_permission("treasury", "ver"))])
async def historial_cobros(vencimiento_id: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    filas = (
        await session.scalars(
            select(CobroPago).where(
                CobroPago.empresa_id == empresa_id,
                CobroPago.vencimiento_id == vencimiento_id,
            ).order_by(CobroPago.fecha)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(c.id),
                "fecha": c.fecha.isoformat(),
                "importe": f"{c.importe:0.4f}",
                "cuenta_tesoreria": c.cuenta_tesoreria,
                "journal_entry_id": str(c.journal_entry_id) if c.journal_entry_id else None,
            }
            for c in filas
        ]
    }


@router.post("/{vencimiento_id}/cobrar", dependencies=[Depends(require_permission("treasury", "editar"))])
async def cobrar(
    vencimiento_id: uuid.UUID,
    body: OperacionBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        op = await registrar_cobro(
            session, empresa_id=empresa_id, vencimiento_id=vencimiento_id,
            fecha=body.fecha, importe=body.importe,
            cuenta_tesoreria=body.cuenta_tesoreria,
            cuenta_bancaria_id=body.cuenta_bancaria_id,
            actor=user.full_name,
        )
    except CobroPagoError as exc:
        _raise(exc)
    return {"id": str(op.id), "importe": f"{op.importe:0.4f}", "asiento_id": str(op.journal_entry_id)}


@router.post("/{vencimiento_id}/pagar", dependencies=[Depends(require_permission("treasury", "editar"))])
async def pagar(
    vencimiento_id: uuid.UUID,
    body: OperacionBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        op = await registrar_pago(
            session, empresa_id=empresa_id, vencimiento_id=vencimiento_id,
            fecha=body.fecha, importe=body.importe,
            cuenta_tesoreria=body.cuenta_tesoreria,
            cuenta_bancaria_id=body.cuenta_bancaria_id,
            actor=user.full_name,
        )
    except CobroPagoError as exc:
        _raise(exc)
    return {"id": str(op.id), "importe": f"{op.importe:0.4f}", "asiento_id": str(op.journal_entry_id)}
