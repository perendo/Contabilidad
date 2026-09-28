"""REST API de presupuestos y desviaciones (SPEC-026).

Todas las rutas viven bajo ``/api/v1/presupuestos``; la empresa activa sale
siempre de la sesion autenticada (``Depends(get_empresa_id)``, constitucion
III) y **nunca** del path ni del body. Cada ruta lleva guarda RBAC del modulo
``presupuestos`` para que el inventario de no-bypass siga vacio.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from services.budget.cierre_periodo import cerrar_periodo_desviaciones
from services.budget.desviaciones import calcular_desviaciones, obtener_periodo_actual
from services.budget.errores import PresupuestoError
from services.budget.informe_desviacion import (
    filas_desde_snapshot,
    generar_informe_desviacion,
)
from services.budget.periodos import crear_periodo, listar_periodos, obtener_periodo
from services.budget.presupuesto_service import (
    guardar_presupuesto,
    importar_presupuesto,
    listar_presupuestos,
    parsear_csv,
)
from services.budget.utils import c4

router = APIRouter(prefix="/api/v1/presupuestos", tags=["presupuestos"])

Db = Annotated[AsyncSession, Depends(get_db)]
Empresa = Annotated[int, Depends(get_empresa_id)]

__all__ = ["Db", "Empresa", "router"]

ACTOR = "sistema"


def _http(exc: PresupuestoError) -> HTTPException:
    detalle = {"code": exc.code, "detail": exc.message, **exc.extra}
    return HTTPException(status_code=exc.status_code, detail=detalle)


class PresupuestoBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    cuenta_id: int = Field(gt=0)
    centro_coste_id: str | None = None
    importe: str
    tipo: str | None = Field(default=None, max_length=20)
    observaciones: str | None = Field(default=None, max_length=500)


class ImportarBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    lineas: list[dict[str, Any]] = Field(default_factory=list)


class CerrarBody(BaseModel):
    ejercicio: int | None = Field(default=None, ge=2000, le=2100)
    periodo_id: str


class PeriodoBody(BaseModel):
    ejercicio: int = Field(ge=2000, le=2100)
    fecha_inicio: date
    fecha_fin: date
    notas: str | None = Field(default=None, max_length=500)


# --- US1: presupuesto anual ----------------------------------------------


@router.get(
    "",
    dependencies=[Depends(require_permission("presupuestos", "ver"))],
)
async def listar_ep(
    db: Db,
    empresa_id: Empresa,
    ejercicio: int | None = None,
    cuenta_id: int | None = None,
    centro_coste_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    try:
        return await listar_presupuestos(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            cuenta_id=cuenta_id,
            centro_coste_id=centro_coste_id,
            page=page,
            page_size=page_size,
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("presupuestos", "crear"))],
)
async def guardar_ep(body: PresupuestoBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        presupuesto = await guardar_presupuesto(
            db,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            cuenta_id=body.cuenta_id,
            centro_coste_id=body.centro_coste_id,
            importe=body.importe,
            tipo=body.tipo,
            actor=ACTOR,
            observaciones=body.observaciones,
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc
    return {
        "id": str(presupuesto.id),
        "ejercicio": presupuesto.ejercicio,
        "cuenta_id": presupuesto.cuenta_id,
        "centro_coste_id": str(presupuesto.centro_coste_id)
        if presupuesto.centro_coste_id
        else None,
        "importe": f"{c4(presupuesto.importe):0.4f}",
        "tipo": presupuesto.tipo.value,
        "periodo_id": str(presupuesto.periodo_id) if presupuesto.periodo_id else None,
    }


@router.post(
    "/importar",
    dependencies=[Depends(require_permission("presupuestos", "importar_exportar"))],
)
async def importar_ep(request: Request, db: Db, empresa_id: Empresa) -> Any:
    """Importacion masiva CSV (multipart `file`) o JSON (`{ejercicio, lineas}`)."""
    try:
        content_type = (request.headers.get("content-type") or "").lower()
        ejercicio: int | None = None
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            archivo = form.get("file")
            if archivo is None or isinstance(archivo, str):
                raise PresupuestoError("fichero_invalido", "Falta el fichero 'file'", 422)
            crudo = (await archivo.read()).decode("utf-8-sig", errors="replace").strip()
            if crudo.startswith(("{", "[")):
                filas = _lineas_de_json(crudo)
                ejercicio = _ejercicio_de_json(crudo)
            else:
                filas = parsear_csv(crudo)
                ejercicio = _entero(form.get("ejercicio"))
                if ejercicio is None:
                    # El quickstart de la spec envia solo el fichero; el nombre
                    # `presupuesto_2026.csv` declara el ejercicio.
                    ejercicio = _ejercicio_de_nombre(getattr(archivo, "filename", "") or "")
        else:
            crudo = (await request.body()).decode("utf-8-sig", errors="replace")
            filas = _lineas_de_json(crudo)
            ejercicio = _ejercicio_de_json(crudo)
        if ejercicio is None:
            raise PresupuestoError(
                "parametro_invalido", "Falta el campo ejercicio (2000-2100)", 422
            )
        return await importar_presupuesto(
            db, empresa_id=empresa_id, ejercicio=ejercicio, filas=filas, actor=ACTOR
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc


def _lineas_de_json(crudo: str) -> list[dict[str, Any]]:
    try:
        cuerpo = json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise PresupuestoError("json_invalido", "El cuerpo no es JSON valido", 422) from exc
    if isinstance(cuerpo, list):
        lineas = cuerpo
    elif isinstance(cuerpo, dict):
        lineas = cuerpo.get("lineas") or cuerpo.get("items") or []
    else:  # pragma: no cover - defensivo
        raise PresupuestoError("json_invalido", "Estructura JSON no soportada", 422)
    if not isinstance(lineas, list):
        raise PresupuestoError("json_invalido", "'lineas' debe ser una lista", 422)
    salida: list[dict[str, Any]] = []
    for posicion, fila in enumerate(lineas, start=1):
        if not isinstance(fila, dict):
            raise PresupuestoError(
                "fila_invalida", f"Fila {posicion}: se esperaba un objeto", 422
            )
        salida.append({"fila": posicion, **fila})
    return salida


def _ejercicio_de_json(crudo: str) -> int | None:
    try:
        cuerpo = json.loads(crudo)
    except json.JSONDecodeError:  # pragma: no cover - ya validado
        return None
    if isinstance(cuerpo, dict):
        return _entero(cuerpo.get("ejercicio"))
    return None


def _ejercicio_de_nombre(nombre: str) -> int | None:
    """Ejercicio declarado en el nombre del fichero (`presupuesto_2026.csv`).

    Convencion documentada del quickstart: si el CSV no trae el ejercicio como
    columna ni como campo del formulario, se deduce de un ano de 4 digitos en
    el nombre. Sin ese dato la importacion se rechaza con 422.
    """
    encontrado = re.search(r"(?<!\d)(20\d{2}|21\d{2})(?!\d)", nombre)
    return int(encontrado.group(1)) if encontrado else None


def _entero(valor: Any) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError) as exc:
        raise PresupuestoError(
            "parametro_invalido", f"Ejercicio invalido: {valor!r}", 422
        ) from exc


# --- Periodos de seguimiento (necesarios para el ciclo abrir/cerrar) -------


@router.get(
    "/periodos",
    dependencies=[Depends(require_permission("presupuestos", "ver"))],
)
async def listar_periodos_ep(db: Db, empresa_id: Empresa, ejercicio: int | None = None) -> Any:
    periodos = await listar_periodos(db, empresa_id, ejercicio)
    return {
        "items": [
            {
                "periodo_id": str(p.id),
                "ejercicio": p.ejercicio,
                "numero_periodo": int(p.numero_periodo),
                "fecha_inicio": p.fecha_inicio.isoformat(),
                "fecha_fin": p.fecha_fin.isoformat(),
                "estado": p.estado.value,
                "fecha_cierre": p.fecha_cierre.isoformat() if p.fecha_cierre else None,
                "cerrado_por": p.cerrado_por,
                "desviaciones_registradas": int(p.desviaciones_registradas),
            }
            for p in periodos
        ],
        "total": len(periodos),
    }


@router.post(
    "/periodos",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("presupuestos", "crear"))],
)
async def crear_periodo_ep(body: PeriodoBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        periodo = await crear_periodo(
            db,
            empresa_id=empresa_id,
            ejercicio=body.ejercicio,
            fecha_inicio=body.fecha_inicio,
            fecha_fin=body.fecha_fin,
            actor=ACTOR,
            notas=body.notas,
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc
    return {
        "periodo_id": str(periodo.id),
        "ejercicio": periodo.ejercicio,
        "numero_periodo": int(periodo.numero_periodo),
        "fecha_inicio": periodo.fecha_inicio.isoformat(),
        "fecha_fin": periodo.fecha_fin.isoformat(),
        "estado": periodo.estado.value,
    }


# --- US2: seguimiento ------------------------------------------------------


@router.get(
    "/seguimiento",
    dependencies=[Depends(require_permission("presupuestos", "ver"))],
)
async def seguimiento_ep(
    db: Db,
    empresa_id: Empresa,
    ejercicio: int,
    cuenta_id: int | None = None,
    centro_coste_id: str | None = None,
    mes: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> Any:
    try:
        return await calcular_desviaciones(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            cuenta_id=cuenta_id,
            centro_coste_id=centro_coste_id,
            mes=mes,
            page=page,
            page_size=page_size,
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc


@router.get(
    "/seguimiento/periodo",
    dependencies=[Depends(require_permission("presupuestos", "ver"))],
)
async def periodo_actual_ep(db: Db, empresa_id: Empresa, ejercicio: int) -> Any:
    return await obtener_periodo_actual(db, empresa_id, ejercicio)


@router.get(
    "/seguimiento/snapshot",
    dependencies=[Depends(require_permission("presupuestos", "ver"))],
)
async def snapshot_ep(db: Db, empresa_id: Empresa, periodo_id: str) -> Any:
    try:
        periodo = await obtener_periodo(db, empresa_id, periodo_id)
        if periodo is None:
            raise PresupuestoError(
                "periodo_no_encontrado",
                "Periodo de seguimiento inexistente en la empresa activa",
                404,
            )
        items = await filas_desde_snapshot(
            db, empresa_id=empresa_id, periodo_id=periodo.id
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc
    return {"periodo_id": str(periodo.id), "items": items, "total": len(items)}


# --- US3: informes y cierre -----------------------------------------------


@router.get(
    "/informes/desviacion",
    dependencies=[Depends(require_permission("presupuestos", "ver"))],
)
async def informe_ep(
    db: Db,
    empresa_id: Empresa,
    ejercicio: int,
    periodo_id: str | None = None,
    centro_coste_id: str | None = None,
    cuenta_id: int | None = None,
    mes: int | None = None,
    page: int = 1,
    page_size: int = 200,
) -> Any:
    try:
        return await generar_informe_desviacion(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            periodo_id=periodo_id,
            centro_coste_id=centro_coste_id,
            cuenta_id=cuenta_id,
            mes=mes,
            page=page,
            page_size=page_size,
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc


@router.post(
    "/informes/cerrar",
    dependencies=[Depends(require_permission("presupuestos", "cerrar"))],
)
async def cerrar_ep(body: CerrarBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        return await cerrar_periodo_desviaciones(
            db, empresa_id=empresa_id, periodo_id=body.periodo_id, actor=ACTOR
        )
    except PresupuestoError as exc:
        raise _http(exc) from exc
