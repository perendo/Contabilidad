"""Alta de documentos en un asiento (SPEC-030 US1, FR-001..FR-006, FR-011, FR-018).

Un unico POST con N ficheros (research D13): los validos se persisten y los
rechazados vuelven con su `code` (FR-018). Nunca `async with session.begin()`:
el boundary ACID del repositorio es `get_db` + `flush()` (desviacion V1 de
plan.md), de modo que la fila del documento y su traza de auditoria viajan en la
misma transaccion (FR-011).

La operacion **no toca** `journal_entry` ni `journal_entry_line`: adjuntar no
altera el Debe, el Haber, el numero, la fecha ni el estado del asiento
(FR-015, SC-007). Lo unico que se escribe es la tabla hija `documento_asiento`.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.acct.documento import DocumentoAsiento, EstadoDocumento, TipoDocumento
from models.acct.journal import JournalEntry, JournalEntryEstado
from services.audit import registrar_auditoria
from services.documentos.errores import DocumentoError, error
from services.documentos.validacion import (
    validar_fichero,
    validar_importe_informativo,
    validar_nombre,
    validar_texto,
    validar_tipo_documento,
)

#: FR-016 veta el anclaje a cualquier otro punto que no sea el diario
#: (facturas, extractos, vencimientos, modelos fiscales).
ORIGEN_ADMITIDO = "asiento"

OPERACION_ALTA = "ADJUNTAR_DOCUMENTO"


async def _asiento_de_la_empresa(
    session: AsyncSession, empresa_id: int, asiento_id: Any
) -> JournalEntry:
    """Carga el asiento filtrando **siempre** por `empresa_id` (constitucion III).

    research D14: un asiento de otra empresa produce el mismo 404 que uno
    inexistente. Devolver 403 confirmaria su existencia y permitiria enumerar el
    diario del otro tenant (FR-013, SC-003).
    """
    from uuid import UUID

    try:
        identificador = asiento_id if isinstance(asiento_id, UUID) else UUID(str(asiento_id))
    except (TypeError, ValueError) as exc:
        raise error("asiento_no_encontrado", "El asiento no existe", 404) from exc

    asiento = await session.scalar(
        select(JournalEntry).where(
            JournalEntry.id == identificador,
            JournalEntry.empresa_id == empresa_id,
        )
    )
    if asiento is None:
        raise error("asiento_no_encontrado", "El asiento no existe", 404)
    return asiento


async def _huellas_del_asiento(
    session: AsyncSession, empresa_id: int, asiento_id: Any
) -> set[str]:
    return set(
        (
            await session.scalars(
                select(DocumentoAsiento.sha256).where(
                    DocumentoAsiento.empresa_id == empresa_id,
                    DocumentoAsiento.journal_entry_id == asiento_id,
                )
            )
        ).all()
    )


async def adjuntar_documentos(
    session: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: Any,
    ficheros: list[dict[str, Any]],
    tipo_documento: str,
    descripcion: str | None = None,
    importe_informativo: str | None = None,
    actor: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    """Adjunta varios ficheros a un asiento y devuelve aceptados y rechazados.

    `ficheros` es una lista de dicts ``{"nombre", "contenido", "extension"?}``:
    la capa de API ya ha leido el `UploadFile` y no hay mas que multipart que
    interpretar (research D9).

    Los parametros del formulario se validan **una vez**, antes del bucle: un
    `tipo_documento` invalido es un error de la peticion, no de un fichero, asi
    que no se repite en cada rechazo.
    """
    if not ficheros:
        raise error("documento_vacio", "No se ha enviado ningun fichero")

    asiento = await _asiento_de_la_empresa(session, empresa_id, asiento_id)
    tipo = validar_tipo_documento(tipo_documento)
    descripcion_limpia = validar_texto(descripcion, "descripcion", 500)
    importe = validar_importe_informativo(importe_informativo)

    existentes = await _huellas_del_asiento(session, empresa_id, asiento.id)
    activos = await session.scalar(
        select(func.count())
        .select_from(DocumentoAsiento)
        .where(
            DocumentoAsiento.empresa_id == empresa_id,
            DocumentoAsiento.journal_entry_id == asiento.id,
            DocumentoAsiento.estado == EstadoDocumento.activo,
        )
    )
    plazas = settings.documento_max_por_asiento - int(activos or 0)

    aceptados: list[DocumentoAsiento] = []
    rechazados: list[dict[str, str]] = []
    vista_en_este_lote: set[str] = set()

    for fichero in ficheros:
        nombre_bruto = str(fichero.get("nombre") or "").strip() or "documento"
        contenido = fichero.get("contenido") or b""
        if not isinstance(contenido, (bytes, bytearray)):
            # `UploadFile` sin leer devuelve bytes vacios; un str seria un
            # descriptor de fichero, que no es contenido.
            contenido = b""
        try:
            if plazas <= 0:
                raise error(
                    "limite_documentos_alcanzado",
                    f"El asiento ya tiene el maximo de "
                    f"{settings.documento_max_por_asiento} documentos",
                    409,
                )
            nombre = validar_nombre(nombre_bruto)
            metadatos = validar_fichero(
                nombre, bytes(contenido), fichero.get("extension")
            )
            huella = hashlib.sha256(bytes(contenido)).hexdigest()
            if huella in existentes or huella in vista_en_este_lote:
                raise error(
                    "documento_duplicado",
                    "Ya existe un documento con esa huella en este asiento",
                    409,
                )

            documento = DocumentoAsiento(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                contenido=bytes(contenido),
                sha256=huella,
                nombre_original=nombre,
                content_type=str(metadatos["content_type"]),
                extension=str(metadatos["extension"]),
                size_bytes=len(bytes(contenido)),
                num_paginas=metadatos["num_paginas"],
                tipo_documento=tipo,
                descripcion=descripcion_limpia,
                importe_informativo=importe,
                estado=EstadoDocumento.activo,
                created_by=actor,
            )
            session.add(documento)
            await session.flush()

            await registrar_auditoria(
                session,
                empresa_id=empresa_id,
                operacion=OPERACION_ALTA,
                entidad="documento_asiento",
                entidad_id=documento.id,
                payload={
                    "sha256": documento.sha256,
                    "nombre_original": documento.nombre_original,
                    "size_bytes": documento.size_bytes,
                    "extension": documento.extension,
                    "num_paginas": documento.num_paginas,
                    "tipo_documento": tipo.value,
                    "descripcion": descripcion_limpia,
                    "importe_informativo": (
                        f"{importe:0.4f}" if importe is not None else None
                    ),
                    "asiento_id": str(asiento.id),
                    "asiento_estado": asiento.estado.value,
                },
                usuario=actor,
                ip=ip,
            )
            aceptados.append(documento)
            existentes.add(huella)
            vista_en_este_lote.add(huella)
            plazas -= 1
        except DocumentoError as exc:
            # FR-018: el fallo de un fichero no tira la peticion ni lo ya
            # validado. `asiento.id` es un UUID, nunca `None`.
            rechazados.append(
                {"nombre": nombre_bruto, "code": exc.code, "detail": exc.message}
            )

    return {
        "aceptados": [_serializar(doc) for doc in aceptados],
        "rechazados": rechazados,
        "documentos_obligatorios": False,
    }


def _serializar(documento: DocumentoAsiento) -> dict[str, Any]:
    """Objeto de la respuesta. Importes como string de 4 decimales (research D7
    del plan raiz: `Decimal` viaja como cadena, nunca como `float`)."""
    importe: Decimal | None = documento.importe_informativo
    return {
        "id": str(documento.id),
        "asiento_id": str(documento.journal_entry_id),
        "nombre_original": documento.nombre_original,
        "extension": documento.extension,
        "content_type": documento.content_type,
        "size_bytes": documento.size_bytes,
        "num_paginas": documento.num_paginas,
        "sha256": documento.sha256,
        "tipo_documento": documento.tipo_documento.value,
        "descripcion": documento.descripcion,
        "importe_informativo": (
            f"{importe:0.4f}" if importe is not None else None
        ),
        "estado": documento.estado.value,
        "baja_motivo": documento.baja_motivo,
        "baja_usuario": documento.baja_usuario,
        "baja_at": _iso(documento.baja_at),
        "created_by": documento.created_by,
        "created_at": _iso(documento.created_at) or "",
    }


def _iso(momento: datetime | None) -> str | None:
    """UTC con sufijo `Z`. La base de datos es `TIMESTAMPTZ` (constitucion)."""
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "OPERACION_ALTA",
    "ORIGEN_ADMITIDO",
    "JournalEntryEstado",
    "TipoDocumento",
    "adjuntar_documentos",
]
