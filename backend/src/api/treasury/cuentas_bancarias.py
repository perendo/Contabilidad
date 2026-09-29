"""Cuentas bancarias API: gestión de cuentas bancarias por empresa."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from models.iam.user import User
from models.treasury.cuenta_bancaria import CuentaBancaria
from services.treasury.cuentas_bancarias import (
    CuentaBancariaError,
    crear_cuenta_bancaria,
    listar_cuentas_bancarias,
    obtener_cuenta_bancaria,
)

router = APIRouter(prefix="/cuentas-bancarias", tags=["cuentas_bancarias"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]


class CuentaBancariaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    iban: str = Field(..., min_length=15, max_length=34)
    banco: str | None = Field(None, max_length=120)
    bic: str | None = Field(None, max_length=11)
    cuenta_contable: str = Field(default="572", max_length=20)


def _out(cb: CuentaBancaria) -> dict:
    return {
        "id": str(cb.id),
        "empresa_id": cb.empresa_id,
        "nombre": cb.nombre,
        "banco": cb.banco,
        "iban": cb.iban,
        "bic": cb.bic,
        "cuenta_contable": cb.cuenta_contable,
        "activa": cb.activa,
        "created_at": cb.created_at.isoformat() if cb.created_at else None,
    }


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar(
    empresa_id: EmpresaDep,
    session: SesionDep,
    solo_activas: Annotated[bool, Query()] = True,
):
    cuentas = await listar_cuentas_bancarias(session, empresa_id=empresa_id, solo_activas=solo_activas)
    return {"items": [_out(cb) for cb in cuentas]}


@router.get("/{cuenta_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle(cuenta_id: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    cb = await obtener_cuenta_bancaria(session, empresa_id=empresa_id, cuenta_bancaria_id=cuenta_id)
    if cb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta bancaria inexistente")
    return _out(cb)


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("treasury", "editar"))])
async def crear(
    data: CuentaBancariaCreate,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        cb = await crear_cuenta_bancaria(
            session,
            empresa_id=empresa_id,
            nombre=data.nombre,
            iban=data.iban,
            banco=data.banco,
            bic=data.bic,
            cuenta_contable=data.cuenta_contable,
            actor=user.full_name,
        )
    except CuentaBancariaError as exc:
        if exc.code == "iban_duplicado":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return _out(cb)
