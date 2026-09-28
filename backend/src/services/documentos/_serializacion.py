"""Serializacion compartida de `DocumentoAsiento` (SPEC-030).

Vive en su propio modulo y no en `adjuntos.py` ni en `consulta.py` porque los dos
lo necesitan —el alta devuelve el objeto del documento recien creado y la
consulta lo devuelve al listarlo— y duplicarlo invitaba a que las dos copias
divergieran. Es una desviacion menor respecto de `plan.md`, que preveia cinco
modulos en `services/documentos/`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from models.acct.documento import DocumentoAsiento


def iso_utc(momento: datetime | None) -> str | None:
    """UTC con sufijo `Z`. Las columnas son `TIMESTAMPTZ` (constitucion)."""
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def serializar(documento: DocumentoAsiento) -> dict[str, Any]:
    """Objeto de la respuesta, identico en el alta, en el listado y en el
    detalle (`contracts/api-contracts.md` lo exige: "mismo objeto que en el
    alta").

    `importe_informativo` viaja como **string de 4 decimales**: la constitution
    prohibe `float` para importes y el frontend debe poder compararlo sin
    pérdida. `num_paginas` es `null` en imagenes.
    """
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
        "importe_informativo": f"{importe:0.4f}" if importe is not None else None,
        "estado": documento.estado.value,
        "baja_motivo": documento.baja_motivo,
        "baja_usuario": documento.baja_usuario,
        "baja_at": iso_utc(documento.baja_at),
        "created_by": documento.created_by,
        "created_at": iso_utc(documento.created_at) or "",
    }


__all__ = ["iso_utc", "serializar"]
