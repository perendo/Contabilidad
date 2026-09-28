"""Propuestas automáticas de cruce (SPEC-013 US2, research D3)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.treasury.conciliacion import (
    Conciliacion,
    CruceConciliacion,
    CruceEstado,
    CruceOrigen,
    CrucePrioridad,
)
from models.treasury.extracto_bancario import ExtractoBancario
from models.treasury.movimiento_bancario import (
    EstadoMovimiento,
    MovimientoBancario,
    SignoMovimiento,
)

_MAPA_SIGNO = {SignoMovimiento.D: "debe", SignoMovimiento.H: "haber"}


def normalizar_concepto(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", sin_acentos.upper())


async def _codigo_cuenta(db: AsyncSession, empresa_id: int, cuenta_id: int) -> str | None:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.id == cuenta_id
        )
    )
    return cuenta.code if cuenta else None


async def _movimientos_pendientes(
    db: AsyncSession, empresa_id: int, conciliacion: Conciliacion
) -> list[MovimientoBancario]:
    condiciones = [
        MovimientoBancario.empresa_id == empresa_id,
        MovimientoBancario.estado == EstadoMovimiento.pendiente,
    ]
    if conciliacion.extracto_id is not None:
        condiciones.append(MovimientoBancario.extracto_id == conciliacion.extracto_id)
    else:
        extractos = select(ExtractoBancario.id).where(
            ExtractoBancario.empresa_id == empresa_id,
            ExtractoBancario.cuenta_id == conciliacion.cuenta_id,
        )
        condiciones.append(MovimientoBancario.extracto_id.in_(extractos))
    return list((await db.scalars(select(MovimientoBancario).where(*condiciones))).all())


async def _apuntes_disponibles(
    db: AsyncSession, empresa_id: int, conciliacion: Conciliacion, codigo: str
) -> list[JournalEntryLine]:
    conciliados = select(CruceConciliacion.apunte_id).where(
        CruceConciliacion.empresa_id == empresa_id,
        CruceConciliacion.estado == CruceEstado.confirmado,
    )
    return list(
        (
            await db.scalars(
                select(JournalEntryLine)
                .join(
                    JournalEntry,
                    (JournalEntryLine.journal_entry_id == JournalEntry.id)
                    & (JournalEntryLine.empresa_id == JournalEntry.empresa_id),
                )
                .where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.cuenta == codigo,
                    JournalEntryLine.id.not_in(conciliados),
                    JournalEntry.estado == JournalEntryEstado.POSTED,
                    JournalEntry.fecha >= conciliacion.fecha_inicio,
                    JournalEntry.fecha <= conciliacion.fecha_fin,
                )
            )
        ).all()
    )


async def generar_propuestas(
    db: AsyncSession, *, empresa_id: int, conciliacion: Conciliacion
) -> list[CruceConciliacion]:
    """Compute (and persist as `pendiente_confirmar`) non-destructive proposals."""
    codigo = await _codigo_cuenta(db, empresa_id, conciliacion.cuenta_id)
    if codigo is None:
        return []
    movimientos = await _movimientos_pendientes(db, empresa_id, conciliacion)
    apuntes = await _apuntes_disponibles(db, empresa_id, conciliacion, codigo)
    usados = {
        c.movimiento_id
        for c in (
            await db.scalars(
                select(CruceConciliacion).where(
                    CruceConciliacion.empresa_id == empresa_id,
                    CruceConciliacion.conciliacion_id == conciliacion.id,
                )
            )
        ).all()
    }
    propuestas: list[CruceConciliacion] = []
    for mov in movimientos:
        if mov.id in usados:
            continue
        campo = _MAPA_SIGNO[mov.signo]
        for apunte in apuntes:
            importe_apunte = apunte.debe if campo == "debe" else apunte.haber
            if importe_apunte != mov.importe:
                continue
            prioridad = (
                CrucePrioridad.propuesto
                if normalizar_concepto(mov.concepto) in normalizar_concepto(apunte.descripcion or "")
                or normalizar_concepto(apunte.descripcion or "") in normalizar_concepto(mov.concepto)
                else CrucePrioridad.candidato
            )
            cruce = CruceConciliacion(
                empresa_id=empresa_id,
                conciliacion_id=conciliacion.id,
                movimiento_id=mov.id,
                apunte_id=apunte.id,
                importe=mov.importe,
                signo=mov.signo.value,
                origen=CruceOrigen.auto,
                prioridad=prioridad,
                estado=CruceEstado.pendiente_confirmar,
            )
            db.add(cruce)
            usados.add(mov.id)
            propuestas.append(cruce)
            break
    await db.flush()
    return propuestas


async def conciliados_ids(
    db: AsyncSession, empresa_id: int
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    filas = (
        await db.scalars(
            select(CruceConciliacion).where(
                CruceConciliacion.empresa_id == empresa_id,
                CruceConciliacion.estado == CruceEstado.confirmado,
            )
        )
    ).all()
    movs = {c.movimiento_id for c in filas}
    apuntes = {c.apunte_id for c in filas if c.apunte_id is not None}
    return movs, apuntes


def _dec(value: Decimal) -> Decimal:
    return Decimal(value)
