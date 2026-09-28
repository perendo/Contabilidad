"""REST API for the versioned chart of accounts (SPEC-025).

All routes live under ``/api/v1/catalogo``; the active company always comes
from the authenticated session (``Depends(get_empresa_id)``, constitucion III),
never from path or body. Every route carries an RBAC guard over the ``acct``
module so the no-bypass inventory stays empty.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from models.catalog.catalogo_cuenta import CatalogoCuenta
from services.catalog import _comun
from services.catalog.errores import CatalogoError
from services.catalog.importacion_catalogo import (
    decodificar,
    importar_catalogo,
    parsear_csv,
    parsear_json,
)
from services.catalog.reclasificacion_saldos import (
    confirmar_reclasificacion,
    preview_reclasificacion,
)
from services.catalog.registro_version import (
    activar_version,
    detalle_version,
    listar_versiones,
    registrar_version,
)
from services.catalog.resolucion_historica import resolver_version

router = APIRouter(prefix="/api/v1/catalogo", tags=["catalogo"])

Db = Annotated[AsyncSession, Depends(get_db)]
Empresa = Annotated[int, Depends(get_empresa_id)]

__all__ = ["Db", "Empresa", "router"]


def _http(exc: CatalogoError) -> HTTPException:
    extra = dict(exc.extra or {})
    detalle = {"code": exc.code, "detail": exc.message, **extra}
    return HTTPException(status_code=exc.status_code, detail=detalle)


class VersionNuevaBody(BaseModel):
    codigo: str = Field(min_length=1, max_length=20)
    fecha_inicio: date
    fecha_fin: date | None = None
    cuentas: list[dict[str, Any]] = Field(default_factory=list)


class ReclasificarConfirmarBody(BaseModel):
    version_id: str
    ejercicio: int
    items: list[dict[str, Any]] | None = None


def _fecha(valor: Any, campo: str, por_defecto: date | None = None) -> date | None:
    if valor is None or valor == "":
        return por_defecto
    try:
        return date.fromisoformat(str(valor))
    except ValueError as exc:
        raise CatalogoError(
            "parametro_invalido", f"{campo} invalida: {valor!r}", 422
        ) from exc


def _fecha_obligatoria(valor: Any, campo: str) -> date:
    resuelta = _fecha(valor, campo)
    if resuelta is None:
        raise CatalogoError("parametro_invalido", f"Falta el campo {campo}", 422)
    return resuelta


# --- US1: versiones -------------------------------------------------------


@router.get("/versiones", dependencies=[Depends(require_permission("acct", "ver"))])
async def listar_versiones_ep(
    db: Db,
    empresa_id: Empresa,
    estado: str | None = None,
    fecha_inicio_gte: str | None = None,
    fecha_inicio_lte: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    try:
        return await listar_versiones(
            db,
            empresa_id=empresa_id,
            estado=estado,
            fecha_inicio_desde=_fecha(fecha_inicio_gte, "fecha_inicio_gte"),
            fecha_inicio_hasta=_fecha(fecha_inicio_lte, "fecha_inicio_lte"),
            page=max(page, 1),
            page_size=min(max(page_size, 1), 100),
        )
    except CatalogoError as exc:
        raise _http(exc) from exc


@router.post(
    "/versiones",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "crear"))],
)
async def crear_version_ep(body: VersionNuevaBody, db: Db, empresa_id: Empresa) -> Any:
    try:
        return await registrar_version(
            db,
            empresa_id=empresa_id,
            codigo=body.codigo,
            fecha_inicio=body.fecha_inicio,
            fecha_fin=body.fecha_fin,
            operaciones=body.cuentas,
            actor="sistema",
        )
    except CatalogoError as exc:
        raise _http(exc) from exc


@router.get(
    "/versiones/{version_id}",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def detalle_version_ep(version_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        return await detalle_version(db, empresa_id=empresa_id, version_id=version_id)
    except CatalogoError as exc:
        raise _http(exc) from exc


@router.post(
    "/versiones/{version_id}/activar",
    dependencies=[Depends(require_permission("acct", "editar"))],
)
async def activar_version_ep(version_id: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        return await activar_version(
            db, empresa_id=empresa_id, version_id=version_id, actor="sistema"
        )
    except CatalogoError as exc:
        raise _http(exc) from exc


@router.get("/vigente", dependencies=[Depends(require_permission("acct", "ver"))])
async def version_vigente_ep(fecha: str, db: Db, empresa_id: Empresa) -> Any:
    try:
        return await resolver_version(
            db, empresa_id=empresa_id, fecha=_fecha_obligatoria(fecha, "fecha")
        )
    except CatalogoError as exc:
        raise _http(exc) from exc


@router.get("/cuentas", dependencies=[Depends(require_permission("acct", "ver"))])
async def cuentas_version_ep(
    version_id: str, db: Db, empresa_id: Empresa, q: str = ""
) -> Any:
    try:
        version = await _comun.obtener_version(db, empresa_id, version_id)
        if version is None:
            raise CatalogoError(
                "version_no_encontrada", "Version inexistente en la empresa activa", 404
            )
        consulta = select(CatalogoCuenta).where(
            CatalogoCuenta.empresa_id == empresa_id,
            CatalogoCuenta.version_id == version.id,
        )
        if q:
            busqueda = f"%{q}%"
            consulta = consulta.where(
                or_(
                    CatalogoCuenta.codigo_version.like(busqueda),
                    CatalogoCuenta.nombre_version.like(busqueda),
                )
            )
        filas = (
            await db.scalars(
                consulta.order_by(CatalogoCuenta.codigo_version).limit(50)
            )
        ).all()
        return {
            "items": [
                {
                    "account_id": f.account_id,
                    "codigo_version": f.codigo_version,
                    "nombre_version": f.nombre_version,
                    "estado": f.estado.value,
                }
                for f in filas
            ]
        }
    except CatalogoError as exc:
        raise _http(exc) from exc


# --- US2: importacion normativa ------------------------------------------


@router.post(
    "/importar",
    dependencies=[Depends(require_permission("acct", "importar_exportar"))],
)
async def importar_ep(request: Request, db: Db, empresa_id: Empresa) -> Any:
    try:
        content_type = (request.headers.get("content-type") or "").lower()
        operaciones: list[dict[str, Any]]
        mapeo: list[dict[str, Any]]
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            archivo = form.get("file")
            if archivo is None or isinstance(archivo, str):
                raise CatalogoError(
                    "fichero_invalido", "Falta el fichero 'file'", 422
                )
            texto = decodificar(await archivo.read()).strip()
            codigo_version = str(form.get("codigo_version") or "").strip()
            fecha_inicio = _fecha(form.get("fecha_inicio"), "fecha_inicio")
            fecha_fin = _fecha(form.get("fecha_fin"), "fecha_fin")
            if texto.startswith("{"):
                parsed = parsear_json(texto)
                operaciones = [o.model_dump() for o in parsed.operaciones]
                mapeo = [m.model_dump() for m in parsed.mapeo]
                codigo_version = codigo_version or parsed.codigo_version
                fecha_inicio = fecha_inicio or parsed.fecha_inicio
                fecha_fin = fecha_fin if fecha_fin is not None else parsed.fecha_fin
            else:
                operaciones = parsear_csv(texto)
                mapeo = []
            if not codigo_version:
                raise CatalogoError(
                    "parametro_invalido", "Falta el campo codigo_version", 422
                )
            fecha_inicio = _fecha_obligatoria(fecha_inicio, "fecha_inicio")
        else:
            payload = parsear_json(
                (await request.body()).decode("utf-8-sig", errors="replace")
            )
            codigo_version = payload.codigo_version
            fecha_inicio = payload.fecha_inicio
            fecha_fin = payload.fecha_fin
            operaciones = [o.model_dump() for o in payload.operaciones]
            mapeo = [m.model_dump() for m in payload.mapeo]
        return await importar_catalogo(
            db,
            empresa_id=empresa_id,
            codigo_version=codigo_version,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            operaciones=operaciones,
            mapeo=mapeo,
            actor="sistema",
        )
    except CatalogoError as exc:
        raise _http(exc) from exc


# --- US3: reclasificacion de saldos ---------------------------------------


@router.get(
    "/reclasificar/preview",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def preview_reclasificar_ep(
    version_id: str, ejercicio: int, db: Db, empresa_id: Empresa
) -> Any:
    try:
        return await preview_reclasificacion(
            db, empresa_id=empresa_id, version_id=version_id, ejercicio=ejercicio
        )
    except CatalogoError as exc:
        raise _http(exc) from exc


@router.post(
    "/reclasificar/confirmar",
    dependencies=[Depends(require_permission("acct", "crear"))],
)
async def confirmar_reclasificar_ep(
    body: ReclasificarConfirmarBody, db: Db, empresa_id: Empresa
) -> Any:
    try:
        return await confirmar_reclasificacion(
            db,
            empresa_id=empresa_id,
            version_id=body.version_id,
            ejercicio=body.ejercicio,
            items=body.items,
            actor="sistema",
        )
    except CatalogoError as exc:
        raise _http(exc) from exc
