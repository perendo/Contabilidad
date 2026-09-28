"""Consulta y descarga de documentos (SPEC-030 US2, FR-007, FR-008, FR-017, FR-019).

Cuatro lecturas, todas con el filtro `empresa_id == empresa_id` **obligatorio**
(constitucion III) y las cuatro con `None` —no 403, no datos— cuando el recurso
es de otra empresa (research D14): un 403 confirmaria su existencia y permitiria
enumerar la evidencia ajena (FR-013, SC-003).

El filtro por `ejercicio` se resuelve con `JOIN` a `journal_entry` porque el
ejercicio es columna del **asiento**, no del documento: los documentos de un
asiento de 2025 tienen que aparecer al filtrar por 2025 aunque se adjuntaran
despues (contracts/api-contracts.md seccion 3).

Orden estable `created_at, id` en ambos listados (research D15): `id` es UUID y
actua de desempate, de modo que dos documentos con la misma marca de tiempo
mantienen el orden entre peticiones.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.documento import (
    DocumentoAsiento,
    EstadoDocumento,
    TipoDocumento,
)
from models.acct.journal import JournalEntry
from services.documentos._serializacion import serializar
from services.documentos.errores import DocumentoError, error

#: `page_size` acotado (contracts seccion 3).
PAGE_SIZE_MAX = 100
PAGE_SIZE_DEFECTO = 20

#: Longitud maxima de la busqueda libre.
Q_MAX = 200

#: research D14: mismo texto para "no existe" y "es de otra empresa". Un 403
#: confirmaria la existencia del recurso y permitiria enumerar la evidencia de
#: otro tenant (FR-013, SC-003). Vive en el servicio para que la baja de US3
#: comparta exactamente la misma cadena.
NO_EXISTE = "El documento no existe o pertenece a otra empresa"


def _base(empresa_id: int) -> Select[tuple[DocumentoAsiento]]:
    return select(DocumentoAsiento).where(DocumentoAsiento.empresa_id == empresa_id)


def _encabezado(asiento: JournalEntry) -> dict[str, Any]:
    return {
        "id": str(asiento.id),
        "numero": asiento.numero_asiento,
        "fecha": asiento.fecha.isoformat(),
        "ejercicio": asiento.ejercicio,
        "concepto": asiento.concepto,
        "estado": asiento.estado.value,
    }


async def listar_documentos_asiento(
    session: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: Any,
    incluir_bajas: bool = True,
) -> dict[str, Any]:
    """Documentos de un asiento, con `total` y la_bandera de opcionalidad.

    research D11: un asiento sin documentos devuelve
    `{"items": [], "total": 0, "documentos_obligatorios": false}` y **nunca**
    404. `documentos_obligatorios` viaja siempre en `false` para que el cliente
    no pueda tratar la ausencia como un requisito pendiente (FR-020).
    """
    import uuid

    try:
        identificador = (
            asiento_id if isinstance(asiento_id, uuid.UUID) else uuid.UUID(str(asiento_id))
        )
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

    consulta = _base(empresa_id).where(DocumentoAsiento.journal_entry_id == asiento.id)
    if not incluir_bajas:
        consulta = consulta.where(DocumentoAsiento.estado == EstadoDocumento.activo)
    filas = (
        await session.scalars(consulta.order_by(DocumentoAsiento.created_at, DocumentoAsiento.id))
    ).all()
    return {
        "items": [serializar(fila) for fila in filas],
        "total": len(filas),
        "documentos_obligatorios": False,
    }


async def listar_documentos(
    session: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: Any | None = None,
    ejercicio: int | None = None,
    tipo_documento: str | None = None,
    estado: str | None = None,
    q: str | None = None,
    incluir_bajas: bool = True,
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFECTO,
) -> dict[str, Any]:
    """Listado global con filtros, paginado y orden estable (FR-017, FR-019)."""
    import uuid

    if page < 1:
        raise error("pagina_invalida", "El numero de pagina debe ser 1 o mayor")
    if page_size < 1 or page_size > PAGE_SIZE_MAX:
        raise error(
            "page_size_invalido",
            f"El tamano de pagina debe estar entre 1 y {PAGE_SIZE_MAX}",
        )

    tipo: TipoDocumento | None = None
    if tipo_documento is not None and str(tipo_documento).strip():
        try:
            tipo = TipoDocumento(str(tipo_documento).strip().lower())
        except ValueError as exc:
            admitidos = ", ".join(m.value for m in TipoDocumento)
            raise error(
                "tipo_documento_invalido",
                f"Tipo '{tipo_documento}' no valido. Valores: {admitidos}",
            ) from exc

    estado_filtrado: EstadoDocumento | None = None
    if estado is not None and str(estado).strip():
        try:
            estado_filtrado = EstadoDocumento(str(estado).strip().lower())
        except ValueError as exc:
            raise error(
                "estado_invalido", "El estado debe ser 'activo' o 'dado_de_baja'"
            ) from exc

    # El ejercicio vive en el asiento, no en el documento: JOIN en vez de
    # filtrar `created_at`, que daria un resultado distinto segun cuando se
    # adjuntara. El JOIN es interno y siempre cumple por la FK compuesta, y
    # proyectar `JournalEntry` permite devolver el encabezado del asiento con
    # cada item (FR-019).
    consulta = select(DocumentoAsiento, JournalEntry).join(
        JournalEntry, JournalEntry.id == DocumentoAsiento.journal_entry_id
    ).where(DocumentoAsiento.empresa_id == empresa_id)
    if ejercicio is not None:
        consulta = consulta.where(JournalEntry.ejercicio == ejercicio)
    if asiento_id is not None:
        try:
            consulta = consulta.where(
                DocumentoAsiento.journal_entry_id
                == (
                    asiento_id
                    if isinstance(asiento_id, uuid.UUID)
                    else uuid.UUID(str(asiento_id))
                )
            )
        except (TypeError, ValueError) as exc:
            raise error("documento_no_encontrado", "El documento no existe", 404) from exc
    if tipo is not None:
        consulta = consulta.where(DocumentoAsiento.tipo_documento == tipo)
    if estado_filtrado is not None:
        consulta = consulta.where(DocumentoAsiento.estado == estado_filtrado)
    elif not incluir_bajas:
        consulta = consulta.where(DocumentoAsiento.estado == EstadoDocumento.activo)

    if q is not None and q.strip():
        texto = q.strip()[:Q_MAX]
        patron = f"%{texto}%"
        consulta = consulta.where(
            or_(
                DocumentoAsiento.nombre_original.ilike(patron),
                DocumentoAsiento.descripcion.ilike(patron),
            )
        )

    total = int(
        await session.scalar(
            select(func.count()).select_from(consulta.order_by(None).subquery())
        )
        or 0
    )
    filas = (
        (
            await session.execute(
                consulta.order_by(DocumentoAsiento.created_at, DocumentoAsiento.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .unique()
        .all()
    )
    items: list[dict[str, Any]] = []
    for documento, asiento in filas:
        item = serializar(documento)
        item["journal_entry"] = _encabezado(asiento)
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def obtener_documento(
    session: AsyncSession, *, empresa_id: int, documento_id: Any
) -> DocumentoAsiento | None:
    """Un documento por id, o `None` si no existe o es de otra empresa.

    Un documento dado de baja **si** se devuelve: FR-012 obliga a conservar el
    soporte, asi que ocultarlo es cosa del permiso `acct:ver`, no de la
    consulta.
    """
    import uuid

    try:
        identificador = (
            documento_id
            if isinstance(documento_id, uuid.UUID)
            else uuid.UUID(str(documento_id))
        )
    except (TypeError, ValueError):
        return None
    return await session.scalar(
        select(DocumentoAsiento).where(
            DocumentoAsiento.id == identificador,
            DocumentoAsiento.empresa_id == empresa_id,
        )
    )


def datos_documento_para_descarga(documento: DocumentoAsiento) -> dict[str, Any]:
    """Binario y cabeceras de la descarga (contracts/api-contracts.md seccion 5).

    ``nombre`` es el **valor completo** de la cabecera ``Content-Disposition``,
    no el nombre suelto: lo compone `cabecera_disposicion` con la doble forma de
    RFC 6266.

    `X-Documento-SHA256` viaja para que el cliente pueda verificar la integridad
    sin recalcularla (SC-002, SC-004) y `Cache-Control: no-store` evita que un
    navegador o un proxy compartido retenga evidencia de otra empresa (D14).
    """
    return {
        "contenido": bytes(documento.contenido),
        "content_type": documento.content_type,
        "nombre": cabecera_disposicion(documento.nombre_original),
        "sha256": documento.sha256,
    }


#: Caracteres que permitirian inyectar cabeceras HTTP o romper la cabecera
#: `Content-Disposition` (research D18). research D14 lo exige explicitamente.
_HOSTILES = ('"', ";", "\r", "\n")


def _saneado(nombre: str) -> str:
    """Quita lo que rompe la cabecera y acota a los 255 de la columna (D18)."""
    limpio = "".join(c for c in nombre if c not in _HOSTILES).strip()
    return (limpio or "documento")[:255]


def cabecera_disposicion(nombre: str) -> str:
    """`Content-Disposition` conforme a RFC 6266.

    El nombre original se conserva intacto en la base de datos (caso limite de la
    spec: "se conserva el nombre original tal cual se introdujo"), pero una
    cabecera HTTP solo admite ASCII: mandar UTF-8 crudo produce bytes
    inválidos y rompe a los clientes estrictos — un nombre como
    `Factura nº 42 - Société.pdf` llega al navegador como cabecera corrupta.

    De ahi la doble forma que fija la RFC: `filename` con un equivalente ASCII y
    `filename*` con el nombre real en UTF-8 percent-encoded. Los navegadores
    modernosenteen la segunda; los antiguos, la primera.
    """
    limpio = _saneado(nombre)
    ascii_seguro = limpio.encode("ascii", "replace").decode("ascii").replace("?", "_")
    # El `fallback` no puede contener ni comillas ni `;` (ya no quedan) ni
    # caracteres de control, que `_saneado` no filtra: se limpian aqui.
    ascii_seguro = "".join(
        c for c in ascii_seguro if c.isprintable() or c == " "
    ).strip()
    percent = quote(limpio, safe="")
    return f"attachment; filename=\"{ascii_seguro or 'documento'}\"; filename*=UTF-8''{percent}"


__all__ = [
    "PAGE_SIZE_MAX",
    "DocumentoError",
    "cabecera_disposicion",
    "datos_documento_para_descarga",
    "listar_documentos",
    "listar_documentos_asiento",
    "obtener_documento",
    "serializar",
]
