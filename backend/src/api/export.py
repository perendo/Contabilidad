"""API de la exportacion integral del tenant (SPEC-029).

Router unico bajo `/api/v1/exportaciones`. La empresa activa se deriva de la
sesion (JWT + cabecera `X-Empresa-Activa` via `api.deps.get_empresa_id`):
**nunca** del path ni del body (constitucion III). Los errores de dominio de
`services.export.errores` se traducen a 404/409/422 con cuerpo `{code, detail}`
segun `contracts/api-contracts.md`.

Los endpoints que tocan datos contables llevan guard `require_permission` sobre
el modulo `export` del catalogo de SPEC-015, de modo que la introspeccion de
`api.routes_registry` no encuentra ninguna ruta sin cubrir.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.export.config_sii import ConfigSii
from models.export.exportacion import EstadoExportacion, TipoExportacion
from models.export.manifiesto import ManifiestoBloque
from models.iam.user import User
from services.export import persistir as persistir_svc
from services.export import sii as sii_svc
from services.export import verificar as verificar_svc
from services.export.errores import ExportError

router = APIRouter(prefix="/api/v1/exportaciones", tags=["exportaciones"])

Db = Annotated[AsyncSession, Depends(get_db)]
Empresa = Annotated[int, Depends(get_empresa_id)]
Usuario = Annotated[User, Depends(get_current_user)]

__all__ = ["Db", "Empresa", "Usuario", "router"]

ACTOR = "api"


def _http(exc: ExportError) -> HTTPException:
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


class ExportacionBody(BaseModel):
    """Cuerpo del POST: el `empresa_id` nunca viaja (constitucion III)."""

    tipo: str = Field(default="INTEGRAL", max_length=10)
    ejercicio_desde: int | None = Field(default=None, ge=2000, le=2100)
    ejercicio_hasta: int | None = Field(default=None, ge=2000, le=2100)


class ConfigSiiBody(BaseModel):
    obligado_sii: bool = False
    sin_anexo: bool = False
    clave_regimen: str | None = Field(default=None, max_length=10)
    #: NIF de la entidad representante. Es parte de la cabecera que declara la
    #: AEAT, asi que la API lo expone: sin el, `ConfigSii.entidad_representante_id`
    #: quedaba como una columna que nada podia rellenar.
    entidad_representante_id: uuid.UUID | None = None
    fecha_alta: date | None = None


def _actor(request: Request, user: User) -> tuple[str, str | None]:
    """Actor real de la operacion: `users.id` (BIGINT) como texto + IP de origen.

    El data-model declara `creado_por` como "usuario que ejecuta la
    exportacion"; se usa el id autenticado, no una etiqueta fija de la API.
    """
    return (str(user.id), request.client.host if request.client is not None else None)


# --- US1 · generar, listar, descargar ---------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("export", "crear"))],
)
async def crear_exportacion(
    request: Request,
    db: Db,
    empresa_id: Empresa,
    user: Usuario,
    body: ExportacionBody | None = None,
) -> Any:
    """Genera y persiste la exportacion integral de la empresa activa."""
    cuerpo = body or ExportacionBody()
    try:
        tipo = TipoExportacion(cuerpo.tipo)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "tipo_invalido",
                "detail": f"tipo debe ser INTEGRAL o SII (recibido: {cuerpo.tipo!r})",
            },
        ) from None
    actor, ip = _actor(request, user)
    try:
        resultado = await persistir_svc.exportar_tenant(
            db,
            empresa_id=empresa_id,
            tipo=tipo,
            ejercicio_desde=cuerpo.ejercicio_desde,
            ejercicio_hasta=cuerpo.ejercicio_hasta,
            actor=actor,
            ip=ip,
        )
    except ExportError as exc:
        raise _http(exc) from exc
    fila = resultado["exportacion"]
    manifiesto = resultado["manifiesto"]
    contrato = persistir_svc.contrato_cabecera(fila)
    return {
        **contrato,
        "sha256_contenido": resultado["sha256_contenido"],
        "nombre_fichero": fila.nombre_fichero,
        "manifiesto": {
            "formato_version": manifiesto.formato_version,
            "fecha_generacion": manifiesto.fecha_generacion.isoformat(),
            "n_bloques": manifiesto.n_bloques,
            "bloques": [
                {"bloque": linea.bloque, "conteo_registros": linea.conteo_registros}
                for linea in sorted(
                    await _lineas(db, empresa_id, manifiesto.id), key=lambda l: l.bloque
                )
            ],
        },
    }


async def _lineas(db: AsyncSession, empresa_id: int, manifiesto_id: uuid.UUID) -> list[Any]:
    """Lineas del inventario de la cabecera recien creada (respuesta del POST)."""
    return list(
        (
            await db.scalars(
                select(ManifiestoBloque).where(
                    ManifiestoBloque.empresa_id == empresa_id,
                    ManifiestoBloque.manifiesto_id == manifiesto_id,
                )
            )
        ).all()
    )


@router.get("", dependencies=[Depends(require_permission("export", "ver"))])
async def listar(
    db: Db,
    empresa_id: Empresa,
    tipo: str | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    """Listado paginado de las exportaciones de la empresa activa."""
    try:
        return await persistir_svc.listar_exportaciones(
            db,
            empresa_id=empresa_id,
            tipo=tipo,
            estado=estado,
            page=max(page, 1),
            page_size=min(max(page_size, 1), 100),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "filtro_invalido", "detail": str(exc)},
        ) from exc
    except ExportError as exc:
        raise _http(exc) from exc


# --- US3 · configuracion SII (declarada antes que `/{id}`) -------------------


@router.get("/sii/config", dependencies=[Depends(require_permission("export", "ver"))])
async def leer_config_sii(db: Db, empresa_id: Empresa) -> Any:
    """Configuracion SII efectiva de la empresa activa (US3)."""
    config = await sii_svc.config_efectiva(db, empresa_id)
    return config.contrato()


@router.put("/sii/config", dependencies=[Depends(require_permission("export", "configurar"))])
async def guardar_config_sii(body: ConfigSiiBody, db: Db, empresa_id: Empresa) -> Any:
    """Alta o actualizacion de la configuracion SII de la empresa activa."""
    fila = await db.scalar(select(ConfigSii).where(ConfigSii.empresa_id == empresa_id))
    if fila is None:
        fila = ConfigSii(id=uuid.uuid4(), empresa_id=empresa_id)
        db.add(fila)
    fila.obligado_sii = body.obligado_sii
    fila.sin_anexo = body.sin_anexo
    fila.clave_regimen = body.clave_regimen
    fila.entidad_representante_id = body.entidad_representante_id
    fila.fecha_alta = body.fecha_alta
    await db.flush()
    return (await sii_svc.config_efectiva(db, empresa_id)).contrato()


# --- US1 · detalle, descarga ------------------------------------------------


@router.get("/{exportacion_id}", dependencies=[Depends(require_permission("export", "ver"))])
async def detalle(exportacion_id: str, db: Db, empresa_id: Empresa) -> Any:
    """Detalle de una exportacion con su inventario de bloques."""
    try:
        fila = await persistir_svc.obtener_exportacion(
            db, empresa_id, _uuid(exportacion_id)
        )
        manifiesto = await persistir_svc.obtener_manifiesto(db, empresa_id, fila.id)
    except ExportError as exc:
        raise _http(exc) from exc
    cabecera, lineas = manifiesto if manifiesto else (None, [])
    return persistir_svc.detalle_exportacion(fila, cabecera, lineas)


@router.get(
    "/{exportacion_id}/descarga", dependencies=[Depends(require_permission("export", "ver"))]
)
async def descarga(exportacion_id: str, db: Db, empresa_id: Empresa) -> Response:
    """Descarga del ZIP; 409 si la exportacion no esta en estado `lista`."""
    try:
        fila = await persistir_svc.obtener_exportacion(
            db, empresa_id, _uuid(exportacion_id)
        )
        if fila.estado != EstadoExportacion.lista:
            raise ExportError(
                "exportacion_no_descargable",
                (
                    "La exportacion esta en estado "
                    f"'{fila.estado.value}' y no se puede descargar"
                ),
                409,
            )
        blob = await persistir_svc.obtener_blob(db, empresa_id, fila.id)
    except ExportError as exc:
        raise _http(exc) from exc
    return Response(
        content=bytes(blob.contenido),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fila.nombre_fichero}"'},
    )


# --- US2 · verificacion de integridad ---------------------------------------


@router.post(
    "/{exportacion_id}/verificar", dependencies=[Depends(require_permission("export", "ver"))]
)
async def verificar(
    exportacion_id: str,
    request: Request,
    db: Db,
    empresa_id: Empresa,
    user: Usuario,
) -> Any:
    """Verifica huella y conteos del ZIP (US2); 404 si es de otra empresa."""
    actor, ip = _actor(request, user)
    try:
        return await verificar_svc.verificar_exportacion(
            db,
            empresa_id=empresa_id,
            exportacion_id=_uuid(exportacion_id),
            actor=actor,
            ip=ip,
        )
    except ExportError as exc:
        raise _http(exc) from exc


# --- US3 · bloque SII -------------------------------------------------------


@router.get("/{exportacion_id}/sii", dependencies=[Depends(require_permission("export", "ver"))])
async def bloque_sii(exportacion_id: str, db: Db, empresa_id: Empresa) -> Any:
    """Registros AEAT de una exportacion de tipo SII; 422 si no lo es.

    Se leen del **blob inmutable** de la exportacion, no se recalculan: si el
    tenant cambia despues de exportar, la API debe seguir mostrando
    exactamente lo que contiene el ZIP (research D9).
    """
    try:
        fila = await persistir_svc.obtener_exportacion(
            db, empresa_id, _uuid(exportacion_id)
        )
        if fila.tipo != TipoExportacion.SII:
            raise ExportError(
                "exportacion_no_sii",
                "La exportacion no es de tipo SII; regenera con tipo=SII",
                422,
            )
        blob = await persistir_svc.obtener_blob(db, empresa_id, fila.id)
        config, bloques = sii_svc.leer_bloque_sii(bytes(blob.contenido))
    except ExportError as exc:
        raise _http(exc) from exc
    return {
        "exportacion_id": str(fila.id),
        "config": config,
        "bloques_sii": [
            {"nombre": nombre, "conteo": len(registros), "registros": registros}
            for nombre, registros in sorted(bloques.items())
        ],
    }
