from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.fiscal.liquidacion_retenciones import EstadoLiquidacionRetenciones
from models.iam.user import User
from services.fiscal.errores import FiscalISError
from services.fiscal.liquidacion_retenciones import contabilizar_liquidacion
from services.fiscal.modelo_111_gen import (
    descargar_modelo_111,
    generar_modelo_111,
    listar_modelos_111,
    payload_modelo_111,
)
from services.fiscal.modelo_115_gen import (
    descargar_modelo_115,
    generar_modelo_115,
    listar_modelos_115,
    payload_modelo_115,
)
from services.fiscal.modelo_190_gen import (
    descargar_modelo_190,
    generar_modelo_190,
    listar_modelos_190,
    payload_modelo_190,
    validar_nif_perceptores,
)
from services.fiscal.retenciones import (
    acumular_retenciones,
    listar_liquidaciones,
    listar_retenciones_periodo,
    obtener_detalle_liquidacion,
    obtener_liquidacion,
    payload_liquidacion,
    payload_retencion,
)

router = APIRouter(
    prefix="/api/v1/fiscal/retenciones",
    tags=["fiscal"],
    dependencies=[Depends(get_empresa_id)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]
UserDep = Annotated[User, Depends(get_current_user)]

CODIGOS_404 = {
    "liquidacion_no_encontrada",
    "modelo_no_encontrado",
    "empresa_no_encontrada",
    "tercero_no_encontrado",
}
CODIGOS_409 = {
    "liquidacion_ya_existente",
    "modelo_ya_generado",
    "sin_retenciones_arrendamiento",
}


class LiquidacionBody(BaseModel):
    ejercicio: int
    trimestre: int
    notas: str | None = Field(default=None, max_length=2000)


class ModeloLiquidacionBody(BaseModel):
    liquidacion_id: uuid.UUID


class Modelo190Body(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)


class ContabilizarBody(BaseModel):
    fecha_asiento: date
    cuenta_banco: str = Field(default="5720", min_length=1, max_length=16)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _http_error(exc: FiscalISError) -> NoReturn:
    codigo = 404 if exc.code in CODIGOS_404 else 409 if exc.code in CODIGOS_409 else 422
    status_code = int(getattr(exc, "status_code", codigo))
    detalle: dict[str, Any] = {"code": exc.code, "detail": str(exc)}
    extras = getattr(exc, "detalle", None)
    if isinstance(extras, dict):
        detalle.update(extras)
    raise HTTPException(status_code=status_code, detail=detalle)




def _pagina(
    page: int | None,
    page_size: int | None,
    limit: int | None,
    offset: int | None,
) -> tuple[int, int]:
    if limit is not None:
        return (offset or 0) // limit + 1, limit
    return page or 1, page_size or 50


@router.post(
    "/liquidaciones",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("fiscal", "crear"))],
)
async def crear_liquidacion(
    body: LiquidacionBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        liquidacion = await acumular_retenciones(
            session,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            trimestre=body.trimestre,
            actor=user.email,
            ip=_ip(request),
            notas=body.notas,
        )
    except FiscalISError as exc:
        _http_error(exc)
    return payload_liquidacion(liquidacion)


@router.post(
    "/liquidaciones/{liquidacion_id}/contabilizar",
    dependencies=[Depends(require_permission("fiscal", "editar"))],
)
async def contabilizar(
    liquidacion_id: uuid.UUID,
    body: ContabilizarBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        resultado = await contabilizar_liquidacion(
            session,
            empresa_id=empresa_id,
            liquidacion_id=liquidacion_id,
            fecha_asiento=body.fecha_asiento,
            cuenta_banco=body.cuenta_banco,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    estado = resultado["estado"]
    return {
        "asiento_id": str(resultado["asiento_id"]),
        "estado": estado.value if isinstance(estado, EstadoLiquidacionRetenciones) else str(estado),
        "fecha_liquidacion": resultado["fecha_liquidacion"].isoformat(),
        "total_retenciones": f"{resultado['total_retenciones']:0.4f}",
    }


@router.get(
    "/liquidaciones",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def listar(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    trimestre: Annotated[int | None, Query(ge=1, le=4)] = None,
    estado: EstadoLiquidacionRetenciones | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    page_size: Annotated[int | None, Query(ge=1, le=200)] = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int | None, Query(ge=0)] = None,
) -> dict[str, Any]:
    pagina, tamano = _pagina(page, page_size, limit, offset)
    try:
        filas, total = await listar_liquidaciones(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            trimestre=trimestre,
            estado=estado,
            pagina=pagina,
            tamano=tamano,
        )
    except FiscalISError as exc:
        _http_error(exc)
    return {
        "items": [payload_liquidacion(fila) for fila in filas],
        "total": total,
    }


@router.get(
    "/liquidaciones/{liquidacion_id}",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def detalle(
    liquidacion_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        resultado = await obtener_detalle_liquidacion(
            session, empresa_id=empresa_id, liquidacion_id=liquidacion_id
        )
    except FiscalISError as exc:
        _http_error(exc)
    if resultado is None:
        _http_error(FiscalISError("liquidacion_no_encontrada", "La liquidación no existe"))
    return resultado


@router.get(
    "/liquidaciones/{liquidacion_id}/retenciones",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def retenciones(
    liquidacion_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> list[dict[str, Any]]:
    if await obtener_liquidacion(
        session, empresa_id=empresa_id, liquidacion_id=liquidacion_id
    ) is None:
        _http_error(FiscalISError("liquidacion_no_encontrada", "La liquidación no existe"))
    filas = await listar_retenciones_periodo(
        session, empresa_id=empresa_id, liquidacion_id=liquidacion_id
    )
    return [payload_retencion(fila) for fila in filas]


@router.post(
    "/modelos-111",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("fiscal", "crear"))],
)
async def generar_111(
    body: ModeloLiquidacionBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        modelo = await generar_modelo_111(
            session,
            empresa_id=empresa_id,
            liquidacion_id=body.liquidacion_id,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return payload_modelo_111(modelo)


@router.get(
    "/modelos-111",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def listar_111(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    trimestre: Annotated[int | None, Query(ge=1, le=4)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    try:
        filas, total = await listar_modelos_111(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            trimestre=trimestre,
            pagina=page,
            tamano=page_size,
        )
    except FiscalISError as exc:
        _http_error(exc)
    return {"items": [payload_modelo_111(fila) for fila in filas], "total": total}


@router.get(
    "/modelos-111/{modelo_111_id}",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def descargar_111(
    modelo_111_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> Response:
    try:
        contenido, content_type, nombre = await descargar_modelo_111(
            session, empresa_id=empresa_id, modelo_111_id=modelo_111_id
        )
    except FiscalISError as exc:
        _http_error(exc)
    return Response(
        content=contenido,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post(
    "/modelos-115",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("fiscal", "crear"))],
)
async def generar_115(
    body: ModeloLiquidacionBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        modelo = await generar_modelo_115(
            session,
            empresa_id=empresa_id,
            liquidacion_id=body.liquidacion_id,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return payload_modelo_115(modelo)


@router.get(
    "/modelos-115",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def listar_115(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    trimestre: Annotated[int | None, Query(ge=1, le=4)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    try:
        filas, total = await listar_modelos_115(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            trimestre=trimestre,
            pagina=page,
            tamano=page_size,
        )
    except FiscalISError as exc:
        _http_error(exc)
    return {"items": [payload_modelo_115(fila) for fila in filas], "total": total}


@router.get(
    "/modelos-115/{modelo_115_id}",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def descargar_115(
    modelo_115_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> Response:
    try:
        contenido, content_type, nombre = await descargar_modelo_115(
            session, empresa_id=empresa_id, modelo_115_id=modelo_115_id
        )
    except FiscalISError as exc:
        _http_error(exc)
    return Response(
        content=contenido,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get(
    "/modelo-190",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def listar_190(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    try:
        filas, total = await listar_modelos_190(
            session,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            pagina=page,
            tamano=page_size,
        )
    except FiscalISError as exc:
        _http_error(exc)
    return {
        "items": [payload_modelo_190(modelo) for modelo in filas],
        "total": total,
    }


@router.get(
    "/modelo-190/validar",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def validar_190(
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int, Query(ge=2000, le=2100)],
) -> dict[str, Any]:
    try:
        return await validar_nif_perceptores(
            session, empresa_id=empresa_id, ejercicio=ejercicio
        )
    except FiscalISError as exc:
        _http_error(exc)


@router.post(
    "/modelo-190",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("fiscal", "crear"))],
)
async def generar_190(
    body: Modelo190Body,
    request: Request,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: UserDep,
) -> dict[str, Any]:
    try:
        modelo = await generar_modelo_190(
            session,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            actor=user.email,
            ip=_ip(request),
        )
    except FiscalISError as exc:
        _http_error(exc)
    return payload_modelo_190(modelo)


@router.get(
    "/modelo-190/{modelo_190_id}",
    dependencies=[Depends(require_permission("fiscal", "ver"))],
)
async def descargar_190(
    modelo_190_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> Response:
    try:
        contenido, content_type, nombre = await descargar_modelo_190(
            session, empresa_id=empresa_id, modelo_190_id=modelo_190_id
        )
    except FiscalISError as exc:
        _http_error(exc)
    return Response(
        content=contenido,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


__all__ = ["router"]
