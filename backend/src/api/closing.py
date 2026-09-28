"""API de cierres intermedios, cierre anual y reaperturas (SPEC-028).

Router unico bajo `/api/v1/cierres`. La empresa activa se deriva de la sesion
(JWT + cabecera `X-Empresa-Activa` via `api.deps.get_empresa_id`): **nunca**
del path ni del body (constitucion III). Los errores de dominio de
`services.closing.errores` se traducen a 404/409/422 con cuerpo
`{code, detail}` segun `contracts/api-contracts.md`.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from models.closing.balanza_periodo import BalanzaPeriodoLinea
from models.closing.cierre_ejercicio import CierreEjercicio
from models.closing.periodo_cerrado import PeriodoCerrado
from models.closing.solicitud_reapertura import SolicitudReapertura
from services.cashflow.utils import fmt
from services.closing import cierre_anual as cierre_anual_svc
from services.closing import periodo as periodo_svc
from services.closing import reapertura as reapertura_svc
from services.closing.errores import ClosingError

router = APIRouter(prefix="/api/v1/cierres", tags=["cierres"])

Db = Annotated[AsyncSession, Depends(get_db)]
Empresa = Annotated[int, Depends(get_empresa_id)]

__all__ = ["Db", "Empresa", "router"]

ACTOR = "api"


def _http(exc: ClosingError) -> HTTPException:
    detalle = {"code": exc.code, "detail": exc.message, **exc.extra}
    return HTTPException(status_code=exc.status_code, detail=detalle)


def _uuid(valor: str, codigo: str = "parametro_invalido") -> uuid.UUID:
    try:
        return uuid.UUID(str(valor))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": codigo, "detail": f"Identificador no valido: {valor!r}"},
        ) from None


class CerrarIntermedioBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    tipo: str = Field(max_length=20)
    periodo: int = Field(ge=1, le=12)


class CierreAnualBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)


class ReaperturaBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    tipo_periodo: str = Field(max_length=20)
    periodo: int | None = Field(default=None, ge=1, le=12)
    motivo: str | None = Field(default=None, max_length=2000)
    nota_impacto: str | None = Field(default=None, max_length=2000)


class RectificarBody(BaseModel):
    asiento_id: str = Field(max_length=64)


# --- US1 · cierres intermedios --------------------------------------------


@router.post(
    "/intermedios",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("cierres", "crear"))],
)
async def cerrar_intermedio(body: CerrarIntermedioBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        resultado = await periodo_svc.cerrar_periodo_intermedio(
            db,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            tipo=body.tipo,
            periodo=body.periodo,
            actor=ACTOR,
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    fila: PeriodoCerrado = resultado["periodo"]
    balanza = resultado["balanza"]
    return {
        "periodo_id": str(fila.id),
        "ejercicio": fila.ejercicio,
        "tipo": fila.tipo.value,
        "periodo": fila.periodo,
        "fecha_ini": fila.fecha_ini.isoformat(),
        "fecha_fin": fila.fecha_fin.isoformat(),
        "estado": fila.estado.value,
        "n_reaperturas": fila.n_reaperturas,
        "cerrado_at": fila.cerrado_at.isoformat(),
        "balanza": {
            "id": str(balanza.id),
            "total_debe": fmt(balanza.total_debe),
            "total_haber": fmt(balanza.total_haber),
            "cuadra": balanza.total_debe == balanza.total_haber,
            "n_lineas": balanza.n_lineas,
            "sha256": balanza.sha256,
        },
        "resultado_provisional": fmt(balanza.resultado_provisional),
    }


@router.get(
    "/intermedios",
    dependencies=[Depends(require_permission("cierres", "ver"))],
)
async def listar_intermedios(
    db: Db,
    empresa_id: Empresa,
    ejercicio: int | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> Any:
    """Periodos cerrados; `tipo=MES|TRIMESTRE` sin `ejercicio` devuelve el calendario."""
    try:
        if tipo and ejercicio is not None and estado is None:
            items = await periodo_svc.calendario_periodos(
                db, empresa_id=empresa_id, ejercicio=ejercicio, tipo=tipo
            )
            inicio = max(page - 1, 0) * page_size
            return {
                "items": [_periodo_calendar_json(item) for item in items[inicio : inicio + page_size]],
                "total": len(items),
                "page": page,
            }
        resultado = await periodo_svc.listar_periodos(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            tipo=tipo,
            estado=estado,
            page=page,
            page_size=page_size,
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "items": [_periodo_json(fila) for fila in resultado["items"]],
        "total": resultado["total"],
        "page": resultado["page"],
    }


@router.get(
    "/intermedios/{periodo_id}/balanza",
    dependencies=[Depends(require_permission("cierres", "ver"))],
)
async def balanza_intermedio(periodo_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        cabecera, lineas = await periodo_svc.obtener_balanza_periodo(
            db, empresa_id=empresa_id, periodo_id=_uuid(periodo_id)
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "id": str(cabecera.id),
        "periodo_id": str(cabecera.periodo_id),
        "ejercicio": cabecera.ejercicio,
        "fecha_ini": cabecera.fecha_ini.isoformat(),
        "fecha_fin": cabecera.fecha_fin.isoformat(),
        "fecha_generacion": cabecera.fecha_generacion.isoformat(),
        "total_debe": fmt(cabecera.total_debe),
        "total_haber": fmt(cabecera.total_haber),
        "cuadra": cabecera.total_debe == cabecera.total_haber,
        "n_lineas": cabecera.n_lineas,
        "resultado_provisional": fmt(cabecera.resultado_provisional),
        "sha256": cabecera.sha256,
        "lineas": [_linea_json(linea) for linea in lineas],
    }


# --- US2 · cierre anual ---------------------------------------------------


@router.post(
    "/anual",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("cierres", "cerrar"))],
)
async def cerrar_anual(body: CierreAnualBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        resultado = await cierre_anual_svc.generar_cierre_anual(
            db, empresa_id=empresa_id, ejercicio=body.ejercicio, actor=ACTOR
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    fila: CierreEjercicio = resultado["cierre"]
    regularizacion = resultado["asiento_regularizacion"]
    cierre = resultado["asiento_cierre"]
    apertura = resultado["asiento_apertura_id"]
    return {
        "cierre_id": str(fila.id),
        "ejercicio": fila.ejercicio,
        "estado": fila.estado.value,
        "fecha_cierre": fila.fecha_cierre.isoformat(),
        "resultado_ejercicio": fmt(fila.resultado_ejercicio),
        "asiento_regularizacion_id": str(regularizacion.id) if regularizacion is not None else None,
        "asiento_cierre_id": str(cierre.id) if cierre is not None else None,
        "asiento_apertura_id": str(apertura) if apertura is not None else None,
    }


@router.get(
    "/anual/{ejercicio}",
    dependencies=[Depends(require_permission("cierres", "ver"))],
)
async def detalle_anual(ejercicio: int, db: Db, empresa_id: Empresa) -> Any:
    try:
        fila = await cierre_anual_svc.obtener_cierre_anual(
            db, empresa_id=empresa_id, ejercicio=ejercicio
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "cierre_id": str(fila.id),
        "ejercicio": fila.ejercicio,
        "estado": fila.estado.value,
        "fecha_cierre": fila.fecha_cierre.isoformat(),
        "resultado_ejercicio": fmt(fila.resultado_ejercicio),
        "asiento_regularizacion_id": (
            str(fila.asiento_regularizacion_id)
            if fila.asiento_regularizacion_id is not None
            else None
        ),
        "asiento_cierre_id": (
            str(fila.asiento_cierre_id) if fila.asiento_cierre_id is not None else None
        ),
        "asiento_apertura_id": (
            str(fila.asiento_apertura_id) if fila.asiento_apertura_id is not None else None
        ),
        "cerrado_por": fila.cerrado_por,
        "cerrado_at": fila.cerrado_at.isoformat(),
    }


# --- US3 · reaperturas controladas ---------------------------------------


@router.post(
    "/reaperturas",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("cierres", "crear"))],
)
async def solicitar_reapertura(body: ReaperturaBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        fila = await reapertura_svc.solicitar_reapertura(
            db,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            tipo_periodo=body.tipo_periodo,
            periodo=body.periodo,
            motivo=body.motivo,
            nota_impacto=body.nota_impacto,
            actor=ACTOR,
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "solicitud_id": str(fila.id),
        "numero_solicitud": fila.numero_solicitud,
        "ejercicio": fila.ejercicio,
        "tipo_periodo": fila.tipo_periodo.value,
        "periodo": fila.periodo,
        "estado": fila.estado.value,
        "fecha_solicitud": fila.fecha_solicitud.isoformat(),
    }


@router.post(
    "/reaperturas/{solicitud_id}/aprobar",
    dependencies=[Depends(require_permission("cierres", "aprobar"))],
)
async def aprobar_reapertura(solicitud_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        fila = await reapertura_svc.marcar_reabierta(
            db,
            empresa_id=empresa_id,
            solicitud_id=_uuid(solicitud_id),
            actor=ACTOR,
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "solicitud_id": str(fila.id),
        "numero_solicitud": fila.numero_solicitud,
        "estado": fila.estado.value,
        "aprobada_por": fila.aprobada_por,
        "fecha_aprobacion": fila.fecha_aprobacion.isoformat() if fila.fecha_aprobacion else None,
        "periodo_id": str(fila.periodo_id) if fila.periodo_id is not None else None,
    }


@router.post(
    "/reaperturas/{solicitud_id}/rechazar",
    dependencies=[Depends(require_permission("cierres", "aprobar"))],
)
async def rechazar_reapertura(solicitud_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        fila = await reapertura_svc.rechazar_reapertura(
            db,
            empresa_id=empresa_id,
            solicitud_id=_uuid(solicitud_id),
            actor=ACTOR,
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "solicitud_id": str(fila.id),
        "numero_solicitud": fila.numero_solicitud,
        "estado": fila.estado.value,
    }


@router.post(
    "/reaperturas/{solicitud_id}/rectificar",
    dependencies=[Depends(require_permission("cierres", "editar"))],
)
async def rectificar_reapertura(
    solicitud_id: str, body: RectificarBody, db: Db, empresa_id: Empresa
) -> Any:
    try:
        fila = await reapertura_svc.rectificar_reapertura(
            db,
            empresa_id=empresa_id,
            solicitud_id=_uuid(solicitud_id),
            asiento_id=_uuid(body.asiento_id, "asiento_id_invalido"),
            actor=ACTOR,
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "solicitud_id": str(fila.id),
        "numero_solicitud": fila.numero_solicitud,
        "estado": fila.estado.value,
        "asiento_rectificacion_id": (
            str(fila.asiento_rectificacion_id)
            if fila.asiento_rectificacion_id is not None
            else None
        ),
        "fecha_cierre_efectivo": (
            fila.fecha_cierre_efectivo.isoformat() if fila.fecha_cierre_efectivo else None
        ),
    }


@router.get(
    "/reaperturas",
    dependencies=[Depends(require_permission("cierres", "ver"))],
)
async def listar_reaperturas(
    db: Db,
    empresa_id: Empresa,
    ejercicio: int | None = None,
    estado: str | None = None,
    tipo_periodo: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> Any:
    try:
        resultado = await reapertura_svc.listar_solicitudes(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            estado=estado,
            tipo_periodo=tipo_periodo,
            page=page,
            page_size=page_size,
        )
    except ClosingError as exc:
        raise _http(exc) from exc
    return {
        "items": [_solicitud_json(fila) for fila in resultado["items"]],
        "total": resultado["total"],
        "page": resultado["page"],
    }


@router.get(
    "/reaperturas/{solicitud_id}",
    dependencies=[Depends(require_permission("cierres", "ver"))],
)
async def detalle_reapertura(solicitud_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        fila = await reapertura_svc.obtener_solicitud(
            db, empresa_id=empresa_id, solicitud_id=_uuid(solicitud_id)
        )
        detalle = _solicitud_json(fila)
        detalle["periodo_cerrado"] = await _periodo_json_await(db, empresa_id, fila)
    except ClosingError as exc:
        raise _http(exc) from exc
    return detalle


async def _periodo_json_await(
    db: AsyncSession, empresa_id: int, fila: SolicitudReapertura
) -> dict[str, Any] | None:
    """Periodo asociado a la solicitud, con su estado vigente (o `None`)."""
    if fila.periodo_id is None:
        return None
    periodo = await db.scalar(
        select(PeriodoCerrado).where(
            PeriodoCerrado.empresa_id == empresa_id, PeriodoCerrado.id == fila.periodo_id
        )
    )
    return _periodo_json(periodo) if periodo is not None else None


# --- serializadores -------------------------------------------------------


def _periodo_json(fila: PeriodoCerrado) -> dict[str, Any]:
    return {
        "periodo_id": str(fila.id),
        "ejercicio": fila.ejercicio,
        "tipo": fila.tipo.value,
        "periodo": fila.periodo,
        "fecha_ini": fila.fecha_ini.isoformat(),
        "fecha_fin": fila.fecha_fin.isoformat(),
        "estado": fila.estado.value,
        "n_reaperturas": fila.n_reaperturas,
        "balanza_id": str(fila.balanza_id) if fila.balanza_id is not None else None,
        "cerrado_at": fila.cerrado_at.isoformat(),
        "cerrado_por": fila.cerrado_por,
    }


def _periodo_calendar_json(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "periodo_id": str(item["periodo_id"]) if item["periodo_id"] else None,
        "ejercicio": item["ejercicio"],
        "tipo": item["tipo"],
        "periodo": item["periodo"],
        "fecha_ini": item["fecha_ini"].isoformat(),
        "fecha_fin": item["fecha_fin"].isoformat(),
        "estado": item["estado"],
        "n_reaperturas": item["n_reaperturas"],
        "balanza_id": str(item["balanza_id"]) if item["balanza_id"] else None,
        "cerrado_at": item["cerrado_at"].isoformat() if item["cerrado_at"] else None,
        "cerrado_por": item["cerrado_por"],
    }


def _linea_json(linea: BalanzaPeriodoLinea) -> dict[str, Any]:
    return {
        "cuenta_id": int(linea.cuenta_id),
        "codigo": linea.codigo,
        "nombre": linea.nombre,
        "nivel": linea.nivel,
        "debe": fmt(linea.debe),
        "haber": fmt(linea.haber),
        "saldo": fmt(linea.saldo),
    }


def _solicitud_json(fila: SolicitudReapertura) -> dict[str, Any]:
    return {
        "solicitud_id": str(fila.id),
        "numero_solicitud": fila.numero_solicitud,
        "ejercicio": fila.ejercicio,
        "periodo_id": str(fila.periodo_id) if fila.periodo_id is not None else None,
        "tipo_periodo": fila.tipo_periodo.value,
        "periodo": fila.periodo,
        "motivo": fila.motivo,
        "estado": fila.estado.value,
        "usuario_solicitante": fila.usuario_solicitante,
        "fecha_solicitud": fila.fecha_solicitud.isoformat(),
        "aprobada_por": fila.aprobada_por,
        "fecha_aprobacion": fila.fecha_aprobacion.isoformat() if fila.fecha_aprobacion else None,
        "asiento_rectificacion_id": (
            str(fila.asiento_rectificacion_id)
            if fila.asiento_rectificacion_id is not None
            else None
        ),
        "fecha_cierre_efectivo": (
            fila.fecha_cierre_efectivo.isoformat() if fila.fecha_cierre_efectivo else None
        ),
        "nota_impacto": fila.nota_impacto,
    }
