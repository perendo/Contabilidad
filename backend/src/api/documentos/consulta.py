"""GET de documentos adjuntos (SPEC-030 US2).

Las cuatro rutas de lectura, con `require_permission("acct", "ver")`. Ninguna
escribe nada, y ninguna acepta `empresa_id` del cliente: sale siempre de la
sesion (constitucion III).

Orden de declaracion: las estaticas (`""`, `/asiento/{id}`) antes que las de
recurso (`/{documento_id}`), para que el comodin no las capture.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import require_permission
from api.documentos.deps import Db, Empresa, _http
from services.documentos.consulta import (
    NO_EXISTE,
    PAGE_SIZE_DEFECTO,
    PAGE_SIZE_MAX,
    datos_documento_para_descarga,
    listar_documentos,
    listar_documentos_asiento,
    obtener_documento,
    serializar,
)
from services.documentos.errores import DocumentoError

router = APIRouter(prefix="/api/v1/documentos", tags=["documentos"])


@router.get(
    "/asiento/{asiento_id}",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def listar_del_asiento(
    asiento_id: str,
    db: Db,
    empresa_id: Empresa,
    incluir_bajas: Annotated[bool, Query()] = True,
) -> dict:
    """Documentos de un asiento. research D11: sin documentos devuelve 200 con
    `items` vacio y `documentos_obligatorios: false`, nunca 404."""
    try:
        return await listar_documentos_asiento(
            db,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            incluir_bajas=incluir_bajas,
        )
    except DocumentoError as exc:
        raise _http(exc) from exc


@router.get("", dependencies=[Depends(require_permission("acct", "ver"))])
async def listar(
    db: Db,
    empresa_id: Empresa,
    asiento_id: Annotated[uuid.UUID | None, Query()] = None,
    ejercicio: Annotated[int | None, Query(ge=1900, le=2200)] = None,
    tipo_documento: Annotated[str | None, Query()] = None,
    estado: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    incluir_bajas: Annotated[bool, Query()] = True,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFECTO,
) -> dict:
    """Listado global: permite localizar la evidencia sin conocer el numero de
    asiento (FR-019, SC-010)."""
    try:
        return await listar_documentos(
            db,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            ejercicio=ejercicio,
            tipo_documento=tipo_documento,
            estado=estado,
            q=q,
            incluir_bajas=incluir_bajas,
            page=page,
            page_size=page_size,
        )
    except DocumentoError as exc:
        raise _http(exc) from exc


@router.get(
    "/{documento_id}",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def metadatos(documento_id: str, db: Db, empresa_id: Empresa) -> dict:
    try:
        documento = await obtener_documento(
            db, empresa_id=empresa_id, documento_id=documento_id
        )
    except DocumentoError as exc:
        raise _http(exc) from exc
    if documento is None:
        raise _http(DocumentoError("documento_no_encontrado", NO_EXISTE, 404))
    return serializar(documento)


@router.get(
    "/{documento_id}/descarga",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def descarga(documento_id: str, db: Db, empresa_id: Empresa) -> Response:
    """Binario integro, no JSON (contracts/api-contracts.md seccion 5).

    El contenido servido es byte a byte el del alta, de modo que su `sha256`
    coincide con `X-Documento-SHA256` (SC-002). Un documento dado de baja **si**
    se descarga: FR-012 obliga a conservar el soporte y la ocultacion se resuelve
    con el permiso `acct:ver`, no con el almacenamiento.
    """
    try:
        documento = await obtener_documento(
            db, empresa_id=empresa_id, documento_id=documento_id
        )
    except DocumentoError as exc:
        raise _http(exc) from exc
    if documento is None:
        raise _http(DocumentoError("documento_no_encontrado", NO_EXISTE, 404))
    datos = datos_documento_para_descarga(documento)
    return Response(
        content=datos["contenido"],
        media_type=datos["content_type"],
        headers={
            # `datos["nombre"]` ya es el valor completo de la cabecera
            # (`attachment; filename=...; filename*=UTF-8''...`, RFC 6266): no se
            # envuelve otra vez aqui.
            "Content-Disposition": datos["nombre"],
            # research D14: ni navegador ni proxy compartido retienen evidencia.
            "Cache-Control": "no-store",
            "X-Documento-SHA256": datos["sha256"],
        },
        status_code=status.HTTP_200_OK,
    )
