"""Cruce movimiento↔apunte y acoplamiento con SPEC-020 (SPEC-013 US2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntryLine
from models.treasury.conciliacion import (
    Conciliacion,
    ConciliacionEstado,
    CruceConciliacion,
    CruceEstado,
    CruceOrigen,
    CrucePrioridad,
)
from models.treasury.movimiento_bancario import (
    EstadoMovimiento,
    MovimientoBancario,
    SignoMovimiento,
)
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa
from services.audit.writer import audit_escribir
from services.reconciliation.saldos import recalcular_saldos


class CruceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _apunte(db: AsyncSession, empresa_id: int, apunte_id: uuid.UUID) -> JournalEntryLine:
    apunte = await db.scalar(
        select(JournalEntryLine).where(
            JournalEntryLine.empresa_id == empresa_id, JournalEntryLine.id == apunte_id
        )
    )
    if apunte is None:
        raise CruceError("apunte_no_encontrado", "Apunte inexistente en la empresa activa")
    return apunte


async def _notificar_cobro_remesa(
    db: AsyncSession, empresa_id: int, apunte: JournalEntryLine, mov: MovimientoBancario
) -> bool:
    recibo = await db.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.asiento_cobro_id == apunte.journal_entry_id,
        )
    )
    if recibo is None or recibo.estado == ReciboEstado.cobrado:
        return False
    recibo.estado = ReciboEstado.cobrado
    recibo.fecha_cobro = mov.fecha_valor or mov.fecha_operacion
    await db.flush()
    return True


async def confirmar_cruce(
    db: AsyncSession,
    *,
    empresa_id: int,
    conciliacion: Conciliacion,
    movimiento_id: uuid.UUID,
    apunte_id: uuid.UUID,
    origen: CruceOrigen = CruceOrigen.manual,
    actor: str | None = None,
    usuario_id: int | None = None,
) -> CruceConciliacion:
    if conciliacion.estado == ConciliacionEstado.cerrada:
        raise CruceError("periodo_archivado", "El período ya está archivado (inmutable)")
    mov = await db.scalar(
        select(MovimientoBancario).where(
            MovimientoBancario.empresa_id == empresa_id,
            MovimientoBancario.id == movimiento_id,
        )
    )
    if mov is None:
        raise CruceError("movimiento_no_encontrado", "Movimiento inexistente")
    apunte = await _apunte(db, empresa_id, apunte_id)

    importe_apunte = apunte.debe if mov.signo == SignoMovimiento.D else apunte.haber
    if importe_apunte != mov.importe:
        raise CruceError(
            "importe_no_coincide",
            f"Importe del apunte {importe_apunte} != movimiento {mov.importe}",
        )

    existente = await db.scalar(
        select(CruceConciliacion).where(
            CruceConciliacion.empresa_id == empresa_id,
            CruceConciliacion.movimiento_id == movimiento_id,
            CruceConciliacion.estado == CruceEstado.confirmado,
        )
    )
    if existente is not None:
        raise CruceError("movimiento_ya_conciliado", "El movimiento ya está conciliado")

    cruce = await db.scalar(
        select(CruceConciliacion).where(
            CruceConciliacion.empresa_id == empresa_id,
            CruceConciliacion.conciliacion_id == conciliacion.id,
            CruceConciliacion.movimiento_id == movimiento_id,
            CruceConciliacion.estado == CruceEstado.pendiente_confirmar,
        )
    )
    if cruce is None:
        cruce = CruceConciliacion(
            empresa_id=empresa_id,
            conciliacion_id=conciliacion.id,
            movimiento_id=movimiento_id,
            apunte_id=apunte_id,
            importe=mov.importe,
            signo=mov.signo.value,
            origen=origen,
            prioridad=CrucePrioridad.candidato,
        )
        db.add(cruce)
    cruce.apunte_id = apunte_id
    cruce.estado = CruceEstado.confirmado
    cruce.fecha_cruce = datetime.now(timezone.utc).date()
    cruce.usuario_id = usuario_id
    mov.estado = EstadoMovimiento.conciliado
    notificado = await _notificar_cobro_remesa(db, empresa_id, apunte, mov)
    cruce.confirmado_por_remesa = notificado
    await db.flush()
    await recalcular_saldos(db, empresa_id=empresa_id, conciliacion=conciliacion)
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CONFIRMAR_CRUCE",
        entity="cruce_conciliacion",
        entity_id=str(cruce.id),
        payload={"movimiento_id": str(movimiento_id), "apunte_id": str(apunte_id)},
    )
    await db.flush()
    return cruce


async def deshacer_cruce(
    db: AsyncSession,
    *,
    empresa_id: int,
    conciliacion: Conciliacion,
    cruce_id: uuid.UUID,
    actor: str | None = None,
) -> None:
    if conciliacion.estado == ConciliacionEstado.cerrada:
        raise CruceError("periodo_archivado", "El período ya está archivado (inmutable)")
    cruce = await db.scalar(
        select(CruceConciliacion).where(
            CruceConciliacion.empresa_id == empresa_id,
            CruceConciliacion.conciliacion_id == conciliacion.id,
            CruceConciliacion.id == cruce_id,
        )
    )
    if cruce is None:
        raise CruceError("cruce_no_encontrado", "Cruce inexistente en la empresa activa")
    mov = await db.scalar(
        select(MovimientoBancario).where(
            MovimientoBancario.empresa_id == empresa_id,
            MovimientoBancario.id == cruce.movimiento_id,
        )
    )
    if mov is not None:
        mov.estado = EstadoMovimiento.pendiente
    await db.delete(cruce)
    await db.flush()
    await recalcular_saldos(db, empresa_id=empresa_id, conciliacion=conciliacion)
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="DESHACER_CRUCE",
        entity="cruce_conciliacion",
        entity_id=str(cruce_id),
    )
    await db.flush()


def _dec(value: Decimal) -> Decimal:
    return Decimal(value)
