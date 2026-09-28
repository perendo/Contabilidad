"""REST API de prevision de tesoreria, EFE y alertas de liquidez (SPEC-027).

Todas las rutas viven bajo ``/api/v1/tesoreria``; la empresa activa sale
siempre de la sesion autenticada (``Depends(get_empresa_id)``, constitucion
III) y **nunca** del path ni del body. Cada ruta lleva guarda RBAC del modulo
`treasury` (el modulo de negocio de tesoreria en el catalogo de SPEC-015) para
que el inventario de no-bypass de `api/routes_registry.py` siga vacio.

Los importes viajan como cadenas decimales de 4 decimales
(`contracts/api-contracts.md`).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from models.treasury.alerta_liquidez import AlertaLiquidez
from models.treasury.movimiento_prevision import MovimientoPrevision
from models.treasury.prevision import PrevisionTesoreria
from services.cashflow.alertas import (
    gestionar_alerta,
    ignorar_alerta,
    listar_alertas,
)
from services.cashflow.efe import formular_efe, leer_efe
from services.cashflow.errores import CashflowError
from services.cashflow.proyeccion import (
    aplicar_movimiento_manual,
    detalle_prevision,
    generar_prevision,
    listar_previsiones,
    regenerar_prevision,
)
from services.cashflow.utils import fmt

router = APIRouter(prefix="/api/v1/tesoreria", tags=["tesoreria"])

Db = Annotated[AsyncSession, Depends(get_db)]
Empresa = Annotated[int, Depends(get_empresa_id)]

__all__ = ["Db", "Empresa", "router"]

ACTOR = "sistema"


def _http(exc: CashflowError) -> HTTPException:
    detalle = {"code": exc.code, "detail": exc.message, **exc.extra}
    return HTTPException(status_code=exc.status_code, detail=detalle)


def _prevision_json(p: PrevisionTesoreria) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "numero_prevision": int(p.numero_prevision),
        "fecha_generacion": p.fecha_generacion.isoformat(),
        "desde_fecha": p.desde_fecha.isoformat(),
        "hasta_fecha": p.hasta_fecha.isoformat(),
        "granularidad": p.granularidad.value,
        "saldo_inicial": fmt(p.saldo_inicial),
        "saldo_final": fmt(p.saldo_final),
        "origen_saldo_inicial": p.origen_saldo_inicial,
        "estado": p.estado.value,
        "creado_por": p.creado_por,
    }


def _bucket_json(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "fecha": bucket["fecha"].isoformat(),
        "cobros": fmt(bucket["cobros"]),
        "pagos": fmt(bucket["pagos"]),
        "neto": fmt(bucket["neto"]),
        "saldo_acumulado": fmt(bucket["saldo_acumulado"]),
        "alerta": bool(bucket.get("alerta")),
    }


def _excluido_json(fila: MovimientoPrevision) -> dict[str, Any]:
    """Excluido serializado: el motivo queda persistido en el propio movimiento."""
    return {
        "origen": fila.origen.value,
        "tipo": fila.tipo.value,
        "importe": fmt(fila.importe),
        "fecha_prevista": fila.fecha_prevista.isoformat() if fila.fecha_prevista else None,
        "motivo": fila.motivo_exclusion,
        "concepto": fila.concepto,
        "vencimiento_id": str(fila.vencimiento_id) if fila.vencimiento_id else None,
    }


def _alerta_json(alerta: AlertaLiquidez) -> dict[str, Any]:
    return {
        "id": str(alerta.id),
        "fecha": alerta.fecha.isoformat(),
        "saldo_proyectado": fmt(alerta.saldo_proyectado),
        "importe_deficit": fmt(alerta.importe_deficit),
        "estado": alerta.estado.value,
        "accion_sugerida": alerta.accion_sugerida.value,
        "movimiento_origen_id": str(alerta.movimiento_origen_id)
        if alerta.movimiento_origen_id
        else None,
    }


class MovimientoManualBody(BaseModel):
    tipo: str = Field(max_length=20)
    importe: str
    fecha_prevista: date | None = None
    frecuencia: str | None = Field(default=None, max_length=20)
    concepto: str | None = Field(default=None, max_length=200)


class PrevisionBody(BaseModel):
    desde_fecha: date
    hasta_fecha: date
    granularidad: str = Field(default="dia", max_length=10)
    movimientos_manuales: list[MovimientoManualBody] = Field(default_factory=list)


class RegenerarBody(BaseModel):
    hasta_fecha: date | None = None
    granularidad: str | None = Field(default=None, max_length=10)
    #: `None` = conservar el plan manual de la prevision; una lista (incluso
    #: vacia) lo sustituye, que es la forma de desdobrarlo desde la UI.
    movimientos_manuales: list[MovimientoManualBody] | None = None


class AtenderBody(BaseModel):
    accion: str = Field(max_length=30)
    movimiento_id: str | None = None
    nueva_fecha: date | None = None
    importe: str | None = None


class FormularEFEBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    clasificaciones: list[dict[str, Any]] = Field(default_factory=list)


# --- US1: prevision de tesoreria -------------------------------------------


@router.get(
    "/previsiones",
    dependencies=[Depends(require_permission("treasury", "ver"))],
)
async def listar_ep(
    db: Db,
    empresa_id: Empresa,
    estado: str | None = None,
    granularidad: str | None = None,
    desde_fecha: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    try:
        resultado = await listar_previsiones(
            db,
            empresa_id=empresa_id,
            estado=estado,
            granularidad=granularidad,
            desde_fecha=desde_fecha,
            page=page,
            page_size=page_size,
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    return {
        "items": [_prevision_json(p) for p in resultado["items"]],
        "total": resultado["total"],
        "page": resultado["page"],
    }


@router.post(
    "/previsiones",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("treasury", "crear"))],
)
async def generar_ep(body: PrevisionBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        resultado = await generar_prevision(
            db,
            empresa_id=empresa_id,
            desde_fecha=body.desde_fecha,
            hasta_fecha=body.hasta_fecha,
            granularidad=body.granularidad,
            movimientos_manuales=[m.model_dump() for m in body.movimientos_manuales],
            actor=ACTOR,
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    return {
        **_prevision_json(resultado["prevision"]),
        "n_movimientos": resultado["n_movimientos"],
        "n_alertas": len(resultado["alertas"]),
        "excluidos": [
            {
                "origen": e["origen"],
                "tipo": e["tipo"],
                "importe": fmt(e["importe"]),
                "fecha_prevista": e["fecha_prevista"].isoformat()
                if e.get("fecha_prevista")
                else None,
                "motivo": e["motivo"],
                "concepto": e.get("concepto"),
            }
            for e in resultado["excluidos"]
        ],
        "buckets": [_bucket_json(b) for b in resultado["buckets"]],
    }


@router.get(
    "/previsiones/{prevision_id}",
    dependencies=[Depends(require_permission("treasury", "ver"))],
)
async def detalle_ep(prevision_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        detalle = await detalle_prevision(
            db, empresa_id=empresa_id, prevision_id=prevision_id
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    if detalle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "prevision_no_encontrada",
                "detail": "Prevision de tesoreria inexistente en la empresa activa",
            },
        )
    return {
        **_prevision_json(detalle["prevision"]),
        "buckets": [_bucket_json(b) for b in detalle["buckets"]],
        "alertas": [_alerta_json(a) for a in detalle["alertas"]],
        "movimientos": [
            {
                "id": str(m.id),
                "origen": m.origen.value,
                "tipo": m.tipo.value,
                "importe": fmt(m.importe),
                "fecha_prevista": m.fecha_prevista.isoformat() if m.fecha_prevista else None,
                "frecuencia": m.frecuencia.value,
                "concepto": m.concepto,
                "incluido": m.incluido,
            }
            for m in detalle["incluidos"]
        ],
        "excluidos": [_excluido_json(m) for m in detalle["excluidos"]],
    }


@router.post(
    "/previsiones/{prevision_id}/regenerar",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def regenerar_ep(
    prevision_id: str, body: RegenerarBody, db: Db, empresa_id: Empresa
) -> Any:
    try:
        resultado = await regenerar_prevision(
            db,
            empresa_id=empresa_id,
            prevision_id=prevision_id,
            hasta_fecha=body.hasta_fecha,
            granularidad=body.granularidad,
            movimientos_manuales=(
                [m.model_dump() for m in body.movimientos_manuales]
                if body.movimientos_manuales is not None
                else None
            ),
            actor=ACTOR,
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    return {
        **_prevision_json(resultado["prevision"]),
        "n_movimientos": resultado["n_movimientos"],
        "n_alertas": len(resultado["alertas"]),
        "buckets": [_bucket_json(b) for b in resultado["buckets"]],
    }


@router.post(
    "/previsiones/{prevision_id}/movimientos",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("treasury", "crear"))],
)
async def alta_movimiento_ep(
    prevision_id: str, body: MovimientoManualBody, db: Db, empresa_id: Empresa
) -> Any:
    """Alta de un pago recurrente o cobro estimado dentro de la prevision."""
    if body.fecha_prevista is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "fecha_requerida",
                "detail": "Un movimiento previsto necesita 'fecha_prevista'",
            },
        )
    from services.cashflow.proyeccion import obtener_prevision

    try:
        prevision = await obtener_prevision(
            db, empresa_id=empresa_id, prevision_id=prevision_id
        )
        if prevision is None:
            raise CashflowError(
                "prevision_no_encontrada",
                "Prevision de tesoreria inexistente en la empresa activa",
                404,
            )
        movimiento = await aplicar_movimiento_manual(
            db,
            empresa_id=empresa_id,
            prevision_id=prevision.id,
            tipo=body.tipo,
            importe=body.importe,
            fecha_prevista=body.fecha_prevista,
            frecuencia=body.frecuencia or "unico",
            concepto=body.concepto,
            actor=ACTOR,
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    return {
        "id": str(movimiento.id),
        "origen": movimiento.origen.value,
        "tipo": movimiento.tipo.value,
        "importe": fmt(movimiento.importe),
        "fecha_prevista": movimiento.fecha_prevista.isoformat()
        if movimiento.fecha_prevista
        else None,
        "frecuencia": movimiento.frecuencia.value,
        "concepto": movimiento.concepto,
    }


# --- US3: alertas de liquidez ------------------------------------------------


@router.get("/alertas", dependencies=[Depends(require_permission("treasury", "ver"))])
async def alertas_ep(
    db: Db,
    empresa_id: Empresa,
    prevision_id: str | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> Any:
    try:
        resultado = await listar_alertas(
            db,
            empresa_id=empresa_id,
            prevision_id=prevision_id,
            estado=estado,
            page=page,
            page_size=page_size,
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    return {
        "items": [_alerta_json(a) for a in resultado["items"]],
        "total": resultado["total"],
        "page": resultado["page"],
    }


@router.post(
    "/alertas/{alerta_id}/atender",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def atender_ep(alerta_id: str, body: AtenderBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        alerta = await gestionar_alerta(
            db,
            empresa_id=empresa_id,
            alerta_id=alerta_id,
            accion=body.accion,
            movimiento_id=body.movimiento_id,
            nueva_fecha=body.nueva_fecha.isoformat() if body.nueva_fecha else None,
            importe=body.importe,
            actor=ACTOR,
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    return {
        "alerta_id": str(alerta.id),
        "estado": alerta.estado.value,
        "movimiento_id": str(alerta.movimiento_origen_id)
        if alerta.movimiento_origen_id
        else None,
    }


@router.post(
    "/alertas/{alerta_id}/ignorar",
    dependencies=[Depends(require_permission("treasury", "editar"))],
)
async def ignorar_ep(alerta_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        alerta = await ignorar_alerta(db, empresa_id=empresa_id, alerta_id=alerta_id)
    except CashflowError as exc:
        raise _http(exc) from exc
    return {"alerta_id": str(alerta.id), "estado": alerta.estado.value}


# --- US2: informe EFE -------------------------------------------------------


@router.get("/efe", dependencies=[Depends(require_permission("treasury", "ver"))])
async def efe_ep(db: Db, empresa_id: Empresa, ejercicio: int) -> Any:
    try:
        informe = await leer_efe(db, empresa_id=empresa_id, ejercicio=ejercicio)
    except CashflowError as exc:
        raise _http(exc) from exc
    bloques: dict[str, Any] = {}
    for bloque in ("operativa", "inversion", "financiacion"):
        lineas = [linea for linea in informe["lineas"] if linea["bloque"] == bloque]
        bloques[bloque] = {
            "total": fmt(informe["totales"][bloque]),
            "items": [
                {
                    "cuenta_id": linea["cuenta_id"],
                    "codigo_cuenta": linea["codigo_cuenta"],
                    "importe": fmt(linea["importe"]),
                    "override_usuario": linea["override_usuario"],
                }
                for linea in lineas
            ],
        }
    return {
        "ejercicio": informe["ejercicio"],
        "saldo_inicial": fmt(informe["saldo_inicial"]),
        "variacion_neta": fmt(informe["variacion_neta"]),
        "saldo_final": fmt(informe["saldo_final"]),
        "cuadre": informe["cuadre"],
        "sin_conciliar": informe["sin_conciliar"],
        "saldo_conciliacion": fmt(informe["saldo_conciliacion"])
        if informe["saldo_conciliacion"] is not None
        else None,
        "formulado": bool(informe.get("formulado")),
        "informe_id": str(informe["informe_id"]) if informe.get("informe_id") else None,
        "formulado_por": informe.get("formulado_por"),
        "bloques": bloques,
    }


@router.post(
    "/efe/formular", dependencies=[Depends(require_permission("treasury", "cerrar"))]
)
async def formular_efe_ep(body: FormularEFEBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        resultado = await formular_efe(
            db,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            actor=ACTOR,
            clasificaciones=body.clasificaciones,
        )
    except CashflowError as exc:
        raise _http(exc) from exc
    return {
        "informe_id": str(resultado["informe_id"]),
        "estado": resultado["estado"],
        "cuadre": resultado["cuadre"],
        "sin_conciliar": resultado["sin_conciliar"],
        "saldo_inicial": fmt(resultado["saldo_inicial"]),
        "variacion_neta": fmt(resultado["variacion_neta"]),
        "saldo_final": fmt(resultado["saldo_final"]),
        "totales": {k: fmt(v) for k, v in resultado["totales"].items()},
    }
