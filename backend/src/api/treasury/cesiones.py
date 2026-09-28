"""Cesión de cobros API (SPEC-022 US3)."""

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
from models.treasury.cesion import EstadoCesion, TipoComisionCesion
from models.treasury.notificacion_cesion import MedioNotificacion
from services.treasury import cesion as cesion_svc
from services.treasury.cesion import CesionError

router = APIRouter(prefix="/cesiones", tags=["cesiones"])

SesionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class CesionBody(BaseModel):
    entidad_financiera: str = Field(min_length=1, max_length=100)
    fecha_cesion: date
    vencimiento_ids: list[uuid.UUID] = Field(min_length=1)
    comision: str = Field(pattern=r"^\d+(\.\d{1,4})?$")
    tipo_comision: TipoComisionCesion
    notas: str | None = None


class NotificarBody(BaseModel):
    cliente_id: uuid.UUID
    medio: MedioNotificacion
    fecha_notificacion: date
    notas: str | None = None


class SaldarBody(BaseModel):
    fecha_saldado: date


def _http(exc: CesionError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": str(exc)},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def crear_cesion(
    body: CesionBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        cesion = await cesion_svc.registrar_cesion(
            session,
            empresa_id=empresa_id,
            entidad_financiera=body.entidad_financiera,
            fecha_cesion=body.fecha_cesion,
            vencimiento_ids=body.vencimiento_ids,
            comision=body.comision,
            tipo_comision=body.tipo_comision,
            notas=body.notas,
            actor=user.full_name,
        )
    except CesionError as exc:
        _http(exc)
    n = await cesion_svc.contar_vencimientos(
        session, empresa_id=empresa_id, cesion_id=cesion.id
    )
    return {
        "id": str(cesion.id),
        "entidad_financiera": cesion.entidad_financiera,
        "importe_total_cedido": f"{cesion.importe_total_cedido:0.4f}",
        "comision": f"{cesion.comision:0.4f}",
        "importe_neto_recibido": f"{cesion.importe_neto_recibido:0.4f}",
        "asiento_id": str(cesion.asiento_id),
        "n_vencimientos": n,
    }


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_cesiones(
    empresa_id: EmpresaDep,
    session: SesionDep,
    estado: Annotated[EstadoCesion | None, Query()] = None,
    entidad_financiera: Annotated[str | None, Query()] = None,
    fecha_desde: Annotated[date | None, Query()] = None,
    fecha_hasta: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = await cesion_svc.listar_cesiones(
        session,
        empresa_id=empresa_id,
        estado=estado.value if estado else None,
        entidad_financiera=entidad_financiera,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        pagina=(offset // limit) + 1 if limit else 1,
        tamano=limit,
    )
    return {"total": total, "items": items}


@router.get("/{cesion_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_cesion(
    cesion_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SesionDep,
) -> dict[str, Any]:
    try:
        return await cesion_svc.detalle_cesion(
            session, empresa_id=empresa_id, cesion_id=cesion_id
        )
    except CesionError as exc:
        _http(exc)


@router.post(
    "/{cesion_id}/notificar",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def notificar_cesion(
    cesion_id: uuid.UUID,
    body: NotificarBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        notificacion = await cesion_svc.registrar_notificacion(
            session,
            empresa_id=empresa_id,
            cesion_id=cesion_id,
            cliente_id=body.cliente_id,
            medio=body.medio,
            fecha_notificacion=body.fecha_notificacion,
            notas=body.notas,
            actor=user.full_name,
        )
    except CesionError as exc:
        _http(exc)
    return {"notificacion_id": str(notificacion.id), "estado": notificacion.estado.value}


@router.post(
    "/{cesion_id}/saldar",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def saldar_cesion_endpoint(
    cesion_id: uuid.UUID,
    body: SaldarBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        cesion = await cesion_svc.saldar_cesion(
            session,
            empresa_id=empresa_id,
            cesion_id=cesion_id,
            fecha_saldado=body.fecha_saldado,
            actor=user.full_name,
        )
    except CesionError as exc:
        _http(exc)
    return {"estado": cesion.estado.value}