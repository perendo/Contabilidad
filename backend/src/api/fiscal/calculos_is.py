from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.fiscal.ajuste_extracontable import TipoAjusteExtracontable
from models.fiscal.calculo_is import EstadoCalculoIS
from models.iam.user import User
from services.fiscal.errores import FiscalISError
from services.fiscal.impuesto_sociedades import (
    AjusteEntrada,
    agregar_ajuste,
    calcular_is,
    configurar_impuesto_sociedades,
    contabilizar_is,
    eliminar_ajuste,
    listar_ajustes,
    listar_calculos,
    obtener_calculo,
    obtener_configuracion_is,
    payload_ajuste,
    payload_calculo,
    payload_configuracion,
    recalcular_is,
)

router = APIRouter(prefix="/api/v1/fiscal/is/calculos", tags=["fiscal"])
configuracion_router = APIRouter(prefix="/api/v1/fiscal", tags=["fiscal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]
UserDep = Annotated[User, Depends(get_current_user)]

CODIGOS_404 = {
    "calculo_no_encontrado",
    "ajuste_no_encontrado",
    "modelo_no_encontrado",
    "asiento_no_encontrado",
    "empresa_no_encontrada",
}
CODIGOS_409 = {
    "calculo_ya_definitivo",
    "calculo_contabilizado",
    "estado_invalido",
    "ejercicio_no_definido",
    "ejercicio_no_cerrado",
    "modelo_ya_generado",
    "calculo_no_contabilizado",
}


class CalculoCrearBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    provisional: bool = True
    notas: str | None = Field(default=None, max_length=2000)


class AjusteBody(BaseModel):
    tipo: TipoAjusteExtracontable
    descripcion: str = Field(min_length=1, max_length=500)
    referencia_normativa: str | None = Field(default=None, max_length=255)
    importe: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class AjusteEntradaBody(AjusteBody):
    pass


class RecalcularBody(BaseModel):
    ajustes: list[AjusteEntradaBody] = Field(default_factory=list)
    deducciones: list[AjusteEntradaBody] = Field(default_factory=list)


class ContabilizarBody(BaseModel):
    fecha_asiento: date


class AjusteResponse(BaseModel):
    id: str
    tipo: TipoAjusteExtracontable
    descripcion: str
    referencia_normativa: str | None
    importe: str


class CalculoResponse(BaseModel):
    id: str
    ejercicio: int
    resultado_contable: str
    ajustes_positivos: str
    ajustes_negativos: str
    base_imponible: str
    tipo_impositivo: str
    cuota_integra: str
    deducciones: str
    cuota_liquida: str
    pagos_a_cuenta: str
    cuota_diferencial: str
    provisional: bool
    estado: EstadoCalculoIS
    asiento_id: str | None
    notas: str | None
    created_at: str
    updated_at: str
    ajustes: list[AjusteResponse] = Field(default_factory=list)


class CalculoResumenResponse(BaseModel):
    id: str
    ejercicio: int
    base_imponible: str
    cuota_integra: str
    cuota_diferencial: str
    provisional: bool
    estado: EstadoCalculoIS


class CalculosListaResponse(BaseModel):
    items: list[CalculoResumenResponse]
    total: int


class AjusteCreadoResponse(BaseModel):
    id: str
    tipo: TipoAjusteExtracontable
    importe: str


class ContabilizadoResponse(BaseModel):
    asiento_id: str
    estado: EstadoCalculoIS


class EliminarAjusteResponse(BaseModel):
    ok: bool


class ConfiguracionBody(BaseModel):
    tipo_is: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    fecha_vigencia_desde: date
    fecha_vigencia_hasta: date | None = None


class ConfiguracionResponse(BaseModel):
    tipo_is: str
    fecha_vigencia_desde: str
    fecha_vigencia_hasta: str | None


def _ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _http_error(exc: FiscalISError) -> NoReturn:
    codigo = 404 if exc.code in CODIGOS_404 else 409 if exc.code in CODIGOS_409 else 422
    raise HTTPException(
        status_code=codigo,
        detail={"code": exc.code, "detail": str(exc)},
    )


async def _detalle(
    session: AsyncSession, *, empresa_id: int, calculo_is_id: uuid.UUID
) -> dict[str, Any]:
    calculo = await obtener_calculo(
        session, empresa_id=empresa_id, calculo_is_id=calculo_is_id
    )
    if calculo is None:
        raise FiscalISError("calculo_no_encontrado", "El cálculo no existe")
    ajustes = await listar_ajustes(
        session, empresa_id=empresa_id, calculo_is_id=calculo_is_id
    )
    return payload_calculo(calculo, ajustes=ajustes)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CalculoResponse,
    dependencies=[Depends(require_permission("fiscal", "crear"))],
)
async def crear_calculo(
    body: CalculoCrearBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        calculo = await calcular_is(
            session,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            provisional=body.provisional,
            notas=body.notas,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return await _detalle(
        session, empresa_id=empresa_id, calculo_is_id=calculo.id
    )


@router.get(
    "",
    response_model=CalculosListaResponse,
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def listar(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    provisional: bool | None = None,
    estado: EstadoCalculoIS | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    calculos, total = await listar_calculos(
        session,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        provisional=provisional,
        estado=estado,
        pagina=offset // limit + 1,
        tamano=limit,
    )
    return {
        "items": [
            {
                "id": str(calculo.id),
                "ejercicio": calculo.ejercicio,
                "base_imponible": f"{calculo.base_imponible:0.4f}",
                "cuota_integra": f"{calculo.cuota_integra:0.4f}",
                "cuota_diferencial": f"{calculo.cuota_diferencial:0.4f}",
                "provisional": calculo.provisional,
                "estado": calculo.estado,
            }
            for calculo in calculos
        ],
        "total": total,
    }


@router.get(
    "/{calculo_is_id}",
    response_model=CalculoResponse,
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def detalle(
    calculo_is_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await _detalle(
            session, empresa_id=empresa_id, calculo_is_id=calculo_is_id
        )
    except FiscalISError as exc:
        _http_error(exc)


@router.post(
    "/{calculo_is_id}/recalcular",
    response_model=CalculoResponse,
    dependencies=[Depends(require_permission("fiscal", "editar"))],
)
async def recalcular(
    calculo_is_id: uuid.UUID,
    body: RecalcularBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        await recalcular_is(
            session,
            empresa_id=empresa_id,
            calculo_is_id=calculo_is_id,
            ajustes=[
                AjusteEntrada(
                    tipo=item.tipo,
                    descripcion=item.descripcion,
                    referencia_normativa=item.referencia_normativa,
                    importe=item.importe,
                )
                for item in body.ajustes
            ],
            deducciones=[
                AjusteEntrada(
                    tipo=item.tipo,
                    descripcion=item.descripcion,
                    referencia_normativa=item.referencia_normativa,
                    importe=item.importe,
                )
                for item in body.deducciones
            ],
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return await _detalle(
        session, empresa_id=empresa_id, calculo_is_id=calculo_is_id
    )


@router.post(
    "/{calculo_is_id}/ajustes",
    status_code=status.HTTP_201_CREATED,
    response_model=AjusteCreadoResponse,
    dependencies=[Depends(require_permission("fiscal", "editar"))],
)
async def crear_ajuste(
    calculo_is_id: uuid.UUID,
    body: AjusteBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        ajuste = await agregar_ajuste(
            session,
            empresa_id=empresa_id,
            calculo_is_id=calculo_is_id,
            tipo=body.tipo,
            descripcion=body.descripcion,
            referencia_normativa=body.referencia_normativa,
            importe=body.importe,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return {
        "id": str(ajuste.id),
        "tipo": ajuste.tipo,
        "importe": f"{ajuste.importe:0.4f}",
    }


@router.get(
    "/{calculo_is_id}/ajustes",
    response_model=list[AjusteResponse],
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def ajustes(
    calculo_is_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> list[dict[str, Any]]:
    if await obtener_calculo(
        session, empresa_id=empresa_id, calculo_is_id=calculo_is_id
    ) is None:
        _http_error(FiscalISError("calculo_no_encontrado", "El cálculo no existe"))
    filas = await listar_ajustes(
        session, empresa_id=empresa_id, calculo_is_id=calculo_is_id
    )
    return [payload_ajuste(ajuste) for ajuste in filas]


@router.delete(
    "/{calculo_is_id}/ajustes/{ajuste_id}",
    response_model=EliminarAjusteResponse,
    dependencies=[Depends(require_permission("fiscal", "editar"))],
)
async def borrar_ajuste(
    calculo_is_id: uuid.UUID,
    ajuste_id: uuid.UUID,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, bool]:
    try:
        await eliminar_ajuste(
            session,
            empresa_id=empresa_id,
            calculo_is_id=calculo_is_id,
            ajuste_id=ajuste_id,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return {"ok": True}


@router.post(
    "/{calculo_is_id}/contabilizar",
    response_model=ContabilizadoResponse,
    dependencies=[Depends(require_permission("fiscal", "crear"))],
)
async def contabilizar(
    calculo_is_id: uuid.UUID,
    body: ContabilizarBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        calculo = await contabilizar_is(
            session,
            empresa_id=empresa_id,
            calculo_is_id=calculo_is_id,
            fecha_asiento=body.fecha_asiento,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    if calculo.asiento_id is None:
        _http_error(FiscalISError("asiento_no_encontrado", "El asiento no existe"))
    return {"asiento_id": str(calculo.asiento_id), "estado": calculo.estado}


@configuracion_router.get(
    "/configuracion",
    response_model=ConfiguracionResponse,
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def consultar_configuracion(
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, str | None]:
    try:
        config = await obtener_configuracion_is(
            session,
            empresa_id=empresa_id,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return payload_configuracion(config)


@configuracion_router.patch(
    "/configuracion",
    response_model=ConfiguracionResponse,
    dependencies=[Depends(require_permission("fiscal", "configurar"))],
)
async def actualizar_configuracion(
    body: ConfiguracionBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, str | None]:
    try:
        config = await configurar_impuesto_sociedades(
            session,
            empresa_id=empresa_id,
            tipo_is=body.tipo_is,
            fecha_vigencia_desde=body.fecha_vigencia_desde,
            fecha_vigencia_hasta=body.fecha_vigencia_hasta,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return payload_configuracion(config)
