"""Baja logica de un documento (SPEC-030 US3, FR-010, FR-011, FR-012).

No existe borrado fisico: el trigger `trg_documento_asiento_inmutable_delete`
lo rechazaria y FR-012 obliga a conservar el soporte contable durante el plazo
legal de conservacion (art. 30 LGT). La baja marca el documento, guarda el
motivo, el responsable y la fecha, y deja el contenido y su huella
recuperables.

Se admite **solo** sobre un asiento en `DRAFT` (FR-010): la evidencia de un
asiento ya contabilizado no se retira. Si la evidencia es incorrecta, la via
correcta es anular o rectificar el asiento y adjuntar de nuevo, que es lo que
hace el propio diario (constitucion II).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.documento import DocumentoAsiento, EstadoDocumento
from models.acct.journal import JournalEntry, JournalEntryEstado
from services.audit import registrar_auditoria
from services.documentos.consulta import NO_EXISTE
from services.documentos.errores import error
from services.documentos.validacion import BAJA_MOTIVO_MAX, validar_texto

OPERACION_BAJA = "DAR_DE_BAJA_DOCUMENTO"

#: FR-010: un asiento asentado no pierde su soporte. `CANCELLED` tampoco: un
#: asiento anulado sigue siendo evidencia historica de lo que se contabilizo.
ESTADOS_BAJA_PERMITIDOS = (JournalEntryEstado.DRAFT,)


async def dar_de_baja_documento(
    session: AsyncSession,
    *,
    empresa_id: int,
    documento_id: Any,
    motivo: str | None,
    actor: str | None = None,
    ip: str | None = None,
) -> None:
    """Da de baja un documento. No devuelve nada: el endpoint responde 204.

    Filtra por `empresa_id` (constitucion III) y bloquea la fila con
    `with_for_update()` para que dos bajas concurrentes no se pisen. La
    idempotencia es por deteccion: un segundo `DELETE` encuentra el estado ya en
    `dado_de_baja` y responde 404 `documento_no_encontrado`, no 409.
    """
    import uuid

    try:
        identificador = (
            documento_id
            if isinstance(documento_id, uuid.UUID)
            else uuid.UUID(str(documento_id))
        )
    except (TypeError, ValueError) as exc:
        raise error("documento_no_encontrado", NO_EXISTE, 404) from exc

    documento = await session.scalar(
        select(DocumentoAsiento)
        .where(
            DocumentoAsiento.id == identificador,
            DocumentoAsiento.empresa_id == empresa_id,
        )
        .with_for_update()
    )
    if documento is None or documento.estado != EstadoDocumento.activo:
        raise error("documento_no_encontrado", NO_EXISTE, 404)

    motivo_limpio = validar_texto(motivo, "motivo", BAJA_MOTIVO_MAX)
    if motivo_limpio is None:
        raise error(
            "baja_motivo_obligatorio", "El motivo de la baja es obligatorio"
        )

    asiento = await session.scalar(
        select(JournalEntry).where(
            JournalEntry.id == documento.journal_entry_id,
            JournalEntry.empresa_id == empresa_id,
        )
    )
    if asiento is None or asiento.estado not in ESTADOS_BAJA_PERMITIDOS:
        raise error(
            "baja_no_permitida",
            "El soporte de un asiento ya contabilizado no se retira: "
            "anule o rectifique el asiento en su lugar",
            409,
        )

    # Ni `contenido` ni `sha256` se tocan: FR-009 y FR-012.
    documento.estado = EstadoDocumento.dado_de_baja
    documento.baja_motivo = motivo_limpio
    documento.baja_usuario = actor
    documento.baja_at = datetime.now(timezone.utc)
    await session.flush()

    await registrar_auditoria(
        session,
        empresa_id=empresa_id,
        operacion=OPERACION_BAJA,
        entidad="documento_asiento",
        entidad_id=documento.id,
        payload={
            "sha256": documento.sha256,
            "nombre_original": documento.nombre_original,
            "size_bytes": documento.size_bytes,
            "motivo": motivo_limpio,
            "asiento_id": str(documento.journal_entry_id),
            "asiento_estado": asiento.estado.value,
        },
        usuario=actor,
        ip=ip,
    )


__all__ = ["ESTADOS_BAJA_PERMITIDOS", "NO_EXISTE", "OPERACION_BAJA", "dar_de_baja_documento"]
