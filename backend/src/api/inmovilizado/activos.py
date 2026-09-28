"""Endpoints de activos del inmovilizado (SPEC-014).

Cubre el ciclo de vida del activo: alta (201), edición (PATCH, 200),
listado y detalle, cálculo de plan (sin persistir) en las dos variantes
de ruta (``/activos/plan/calcular`` y ``/activos/{id}/plan/calcular``) y
baja/venta (201). La empresa activa proviene de la sesión (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.inmovilizado.deps import get_empresa_id
from database import get_db
from services.inmovilizado import activo as activo_svc
from services.inmovilizado import baja as baja_svc
from services.inmovilizado.errores import InmovilizadoError
from services.inmovilizado.plan import calcular_plan

router = APIRouter(prefix="/activos", tags=["inmovilizado"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


def _http(exc: InmovilizadoError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": exc.message},
    )


class ActivoBase(BaseModel):
    numero_activo: str = Field(min_length=1, max_length=40)
    cuenta_id: int
    descripcion: str = Field(min_length=1, max_length=255)
    fecha_alta: date
    coste_amortizable: str
    vida_util: int = Field(ge=1, le=600)
    metodo: Literal["lineal", "regresivo"]
    porcentaje_regresivo: str | None = None
    cuenta_gasto_id: int | None = None
    cuenta_acumulada_id: int | None = None


class ActivoCreate(ActivoBase):
    pass


class ActivoUpdate(BaseModel):
    descripcion: str | None = Field(default=None, min_length=1, max_length=255)
    vida_util: int | None = Field(default=None, ge=1, le=600)
    coste_amortizable: str | None = None
    metodo: Literal["lineal", "regresivo"] | None = None
    porcentaje_regresivo: str | None = None
    cuenta_gasto_id: int | None = None
    cuenta_acumulada_id: int | None = None


class BajaBody(BaseModel):
    fecha_baja: date
    precio_venta: str | None = None
    tipo: Literal["venta", "retirada"] = "venta"


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("inmovilizado", "crear"))])
async def crear_activo(body: ActivoCreate, empresa_id: EmpresaDep, session: SessionDep) -> dict[str, Any]:
    try:
        return await activo_svc.dar_de_alta(
            session,
            empresa_id=empresa_id,
            numero_activo=body.numero_activo,
            cuenta_id=body.cuenta_id,
            descripcion=body.descripcion,
            fecha_alta=body.fecha_alta,
            coste_amortizable=body.coste_amortizable,
            vida_util=body.vida_util,
            metodo=body.metodo,
            porcentaje_regresivo=body.porcentaje_regresivo,
            cuenta_gasto_id=body.cuenta_gasto_id,
            cuenta_acumulada_id=body.cuenta_acumulada_id,
            actor="api",
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc


@router.get("", dependencies=[Depends(require_permission("inmovilizado", "ver"))])
async def listar_activos(
    empresa_id: EmpresaDep,
    session: SessionDep,
    estado: str | None = None,
    cuenta_id: int | None = None,
    ejercicio_alta: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return await activo_svc.listar_activos(
            session,
            empresa_id=empresa_id,
            estado=estado,
            cuenta_id=cuenta_id,
            ejercicio_alta=ejercicio_alta,
            page=page,
            page_size=page_size,
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc


@router.get("/{activo_id}", dependencies=[Depends(require_permission("inmovilizado", "ver"))])
async def detalle_activo(
    activo_id: uuid.UUID, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    resultado = await activo_svc.obtener_activo(
        session, empresa_id=empresa_id, activo_id=activo_id
    )
    if resultado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "activo_no_encontrado", "detail": "Activo inexistente en la empresa activa"},
        )
    return resultado


@router.patch("/{activo_id}", dependencies=[Depends(require_permission("inmovilizado", "editar"))])
async def editar_activo(
    activo_id: uuid.UUID,
    body: ActivoUpdate,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        resultado = await activo_svc.editar_activo(
            session,
            empresa_id=empresa_id,
            activo_id=activo_id,
            descripcion=body.descripcion,
            vida_util=body.vida_util,
            coste_amortizable=body.coste_amortizable,
            metodo=body.metodo,
            porcentaje_regresivo=body.porcentaje_regresivo,
            cuenta_gasto_id=body.cuenta_gasto_id,
            cuenta_acumulada_id=body.cuenta_acumulada_id,
            actor="api",
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc
    if "plan" in resultado:
        resultado["plan_futuro"] = resultado.pop("plan")
    return resultado


@router.post("/plan/calcular", dependencies=[Depends(require_permission("inmovilizado", "ver"))])
async def calcular_plan_sin_activo(
    body: ActivoBase, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        plan = calcular_plan(
            body.coste_amortizable,
            body.vida_util,
            body.metodo,
            body.porcentaje_regresivo,
            body.fecha_alta,
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc
    return {"plan": plan, "total_amortizable": body.coste_amortizable}


@router.post("/{activo_id}/plan/calcular", dependencies=[Depends(require_permission("inmovilizado", "ver"))])
async def calcular_plan_activo(
    activo_id: uuid.UUID,
    body: ActivoBase,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        activo = await activo_svc.obtener_activo(session, empresa_id=empresa_id, activo_id=activo_id)
    except InmovilizadoError as exc:
        raise _http(exc) from exc
    if activo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "activo_no_encontrado", "detail": "Activo inexistente en la empresa activa"},
        )
    try:
        plan = calcular_plan(
            body.coste_amortizable,
            body.vida_util,
            body.metodo,
            body.porcentaje_regresivo,
            body.fecha_alta,
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc
    return {"plan": plan, "total_amortizable": body.coste_amortizable}


@router.post("/{activo_id}/baja", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("inmovilizado", "baja"))])
async def dar_de_baja(
    activo_id: uuid.UUID,
    body: BajaBody,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await baja_svc.dar_de_baja(
            session,
            empresa_id=empresa_id,
            activo_id=activo_id,
            fecha_baja=body.fecha_baja,
            precio_venta=body.precio_venta,
            tipo=body.tipo,
            actor="api",
        )
    except InmovilizadoError as exc:
        raise _http(exc) from exc


__all__ = ["router"]