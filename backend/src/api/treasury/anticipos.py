"""Anticipos API (SPEC-022 US1/US2)."""

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
from models.treasury.anticipo import EstadoAnticipo, TipoAnticipo
from services.treasury import anticipo as anticipo_svc
from services.treasury.anticipo import AnticipoError
from services.treasury.liquidacion import (
    AplicacionAnticipo,
    LiquidacionError,
    liquidar_anticipo,
    listar_liquidaciones,
)

router = APIRouter(prefix="/anticipos", tags=["anticipos"])

SesionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class AnticipoBody(BaseModel):
    tercero_id: uuid.UUID
    tipo: TipoAnticipo
    fecha: date
    importe: str = Field(pattern=r"^\d+(\.\d{1,4})?$")
    concepto: str = Field(min_length=1, max_length=255)
    cuenta_contable: str | None = Field(default=None, pattern=r"^(407|408|438)$")
    notas: str | None = None


class LiquidarBody(BaseModel):
    aplicaciones: list[AplicacionAnticipo]
    fecha_aplicacion: date


def _http(exc) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": str(exc)},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def crear_anticipo(
    body: AnticipoBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        anticipo = await anticipo_svc.registrar_anticipo(
            session,
            empresa_id=empresa_id,
            tercero_id=body.tercero_id,
            tipo=body.tipo,
            fecha=body.fecha,
            importe=body.importe,
            concepto=body.concepto,
            cuenta_contable=body.cuenta_contable,
            notas=body.notas,
            actor=user.full_name,
        )
    except AnticipoError as exc:
        _http(exc)
    return {
        "id": str(anticipo.id),
        "tipo": anticipo.tipo.value,
        "importe": f"{anticipo.importe:0.4f}",
        "saldo_pendiente": f"{anticipo.saldo_pendiente:0.4f}",
        "asiento_id": str(anticipo.asiento_id),
    }


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_anticipos(
    empresa_id: EmpresaDep,
    session: SesionDep,
    tipo: Annotated[TipoAnticipo | None, Query()] = None,
    estado: Annotated[EstadoAnticipo | None, Query()] = None,
    tercero_id: Annotated[uuid.UUID | None, Query()] = None,
    fecha_desde: Annotated[date | None, Query()] = None,
    fecha_hasta: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items, total = await anticipo_svc.listar_anticipos(
        session,
        empresa_id=empresa_id,
        tipo=tipo,
        estado=estado.value if estado else None,
        tercero_id=tercero_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        pagina=(offset // limit) + 1 if limit else 1,
        tamano=limit,
    )
    return {
        "total": total,
        "items": [
            {
                "id": str(i.id),
                "tercero_id": str(i.tercero_id),
                "tercero_nombre": i.tercero_nombre,
                "tipo": i.tipo,
                "fecha": i.fecha.isoformat(),
                "importe": f"{i.importe:0.4f}",
                "saldo_pendiente": f"{i.saldo_pendiente:0.4f}",
                "estado": i.estado,
                "asiento_id": str(i.asiento_id) if i.asiento_id else None,
            }
            for i in items
        ],
    }


@router.get("/{anticipo_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_anticipo(
    anticipo_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SesionDep,
) -> dict[str, Any]:
    try:
        return await anticipo_svc.detalle_anticipo(
            session, empresa_id=empresa_id, anticipo_id=anticipo_id
        )
    except AnticipoError as exc:
        _http(exc)


@router.get(
    "/{anticipo_id}/liquidaciones",
    dependencies=[Depends(require_permission("treasury", "ver"))],
)
async def liquidaciones_anticipo(
    anticipo_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SesionDep,
) -> list[dict[str, Any]]:
    try:
        return await listar_liquidaciones(
            session, empresa_id=empresa_id, anticipo_id=anticipo_id
        )
    except LiquidacionError as exc:
        _http(exc)


@router.post(
    "/{anticipo_id}/liquidar",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def liquidar_anticipo_endpoint(
    anticipo_id: uuid.UUID,
    body: LiquidarBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        return await liquidar_anticipo(
            session,
            empresa_id=empresa_id,
            anticipo_id=anticipo_id,
            aplicaciones=body.aplicaciones,
            fecha_aplicacion=body.fecha_aplicacion,
            actor=user.full_name,
        )
    except LiquidacionError as exc:
        _http(exc)