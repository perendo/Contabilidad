"""Third-party master API (SPEC-008): alta, consulta, retirada y cambio de NIF."""

from __future__ import annotations

import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.ar.tercero import Tercero
from models.iam.user import User
from services.audit.writer import audit_escribir
from services.thirdparty.alta import TerceroError, crear_tercero
from services.thirdparty.retirada import (
    RetiradaError,
    borrar_tercero,
    inactivar_tercero,
    verificar_movimientos,
)
from services.thirdparty.saldo import consultar_saldo
from services.thirdparty.validacion_nif import (
    normalizar_nif,
    validar_cambio_nif,
    validar_nif,
)

router = APIRouter(prefix="/api/v1/terceros", tags=["terceros"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]


class TerceroCreate(BaseModel):
    nif: str = Field(min_length=1, max_length=20)
    razon_social: str = Field(min_length=1, max_length=200)
    es_cliente: bool = False
    es_proveedor: bool = False
    direcciones: list | None = None
    telefono: str | None = None
    correo: str | None = None
    iban: str | None = None
    bic: str | None = None
    banco: str | None = None
    autofactura: bool = False


class TerceroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nif: str | None
    razon_social: str
    es_cliente: bool
    es_proveedor: bool
    telefono: str | None
    correo: str | None
    iban: str | None
    banco: str | None
    activo: bool


class NifChange(BaseModel):
    nif_nuevo: str = Field(min_length=1, max_length=20)
    justificacion: str = Field(min_length=1, max_length=255)
    permiso_admin: bool = False


def _raise(exc: Exception) -> NoReturn:
    code = getattr(exc, "code", "")
    message = str(exc)
    if code in ("tercero_no_encontrado",):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if code in ("nif_duplicado", "tiene_movimientos"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def _out(tercero: Tercero) -> TerceroOut:
    return TerceroOut(
        id=tercero.id,
        nif=tercero.nif,
        razon_social=tercero.nombre,
        es_cliente=tercero.es_cliente,
        es_proveedor=tercero.es_proveedor,
        telefono=tercero.telefono,
        correo=tercero.correo,
        iban=tercero.iban,
        banco=tercero.banco,
        activo=tercero.activo,
    )


@router.post(
    "",
    response_model=TerceroOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("ar", "crear"))],
)
async def alta_tercero(
    body: TerceroCreate,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        tercero = await crear_tercero(
            session,
            empresa_id=empresa_id,
            nif=body.nif,
            razon_social=body.razon_social,
            es_cliente=body.es_cliente,
            es_proveedor=body.es_proveedor,
            direcciones=body.direcciones,
            telefono=body.telefono,
            correo=body.correo,
            iban=body.iban,
            bic=body.bic,
            banco=body.banco,
            autofactura=body.autofactura,
            actor=user.full_name,
        )
    except TerceroError as exc:
        _raise(exc)
    return _out(tercero)


@router.get("", dependencies=[Depends(require_permission("ar", "ver"))])
async def listar_terceros(
    empresa_id: EmpresaDep,
    session: SesionDep,
    rol: Annotated[str | None, Query(pattern="^(cliente|proveedor)$")] = None,
    activo: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    condiciones = [Tercero.empresa_id == empresa_id]
    if rol == "cliente":
        condiciones.append(Tercero.es_cliente.is_(True))
    elif rol == "proveedor":
        condiciones.append(Tercero.es_proveedor.is_(True))
    if activo is not None:
        condiciones.append(Tercero.activo.is_(activo))
    if q:
        condiciones.append(Tercero.nombre.ilike(f"%{q}%"))
    total = await session.scalar(select(func.count(Tercero.id)).where(*condiciones))
    filas = (
        await session.scalars(
            select(Tercero)
            .where(*condiciones)
            .order_by(Tercero.nombre)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {"total": total or 0, "items": [_out(t) for t in filas]}


@router.get("/{tercero_id}", dependencies=[Depends(require_permission("ar", "ver"))])
async def detalle_tercero(tercero_id: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    tercero = await session.scalar(
        select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.id == tercero_id)
    )
    if tercero is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tercero inexistente")
    saldo = await consultar_saldo(session, empresa_id, tercero_id)
    return {**_out(tercero).model_dump(), "saldo": saldo}


@router.post("/{tercero_id}/retirar", dependencies=[Depends(require_permission("ar", "editar"))])
async def retirar_tercero(
    tercero_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        tercero = await inactivar_tercero(session, empresa_id, tercero_id, user.full_name)
    except RetiradaError as exc:
        _raise(exc)
    return _out(tercero)


@router.delete("/{tercero_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("ar", "baja"))])
async def borrar(tercero_id: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    try:
        await borrar_tercero(session, empresa_id, tercero_id)
    except RetiradaError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{tercero_id}/nif", dependencies=[Depends(require_permission("ar", "editar"))])
async def cambiar_nif(
    tercero_id: uuid.UUID,
    body: NifChange,
    empresa_id: EmpresaDep,
    session: SesionDep,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
):
    tercero = await session.scalar(
        select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.id == tercero_id)
    )
    if tercero is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tercero inexistente")
    nif_nuevo = normalizar_nif(body.nif_nuevo)
    if not validar_nif(nif_nuevo):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="NIF inválido"
        )
    duplicado = await session.scalar(
        select(Tercero.id).where(
            Tercero.empresa_id == empresa_id,
            Tercero.nif == nif_nuevo,
            Tercero.id != tercero_id,
        )
    )
    if duplicado is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="NIF duplicado")
    tiene, _ = await verificar_movimientos(session, empresa_id, tercero_id)
    try:
        validar_cambio_nif(tiene_movimientos=tiene, permiso_admin=body.permiso_admin)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    nif_anterior = tercero.nif
    tercero.nif = nif_nuevo
    await session.flush()
    await audit_escribir(
        session,
        empresa_id=empresa_id,
        actor=user.full_name,
        action="CHANGE_NIF",
        entity="tercero",
        entity_id=str(tercero_id),
        ip=request.client.host if request.client else None,
        payload={
            "nif_anterior": nif_anterior,
            "nif_nuevo": nif_nuevo,
            "justificacion": body.justificacion,
        },
    )
    await session.flush()
    return _out(tercero)
