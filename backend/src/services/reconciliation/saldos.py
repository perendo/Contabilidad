"""Saldos, pendientes e informe de conciliación (SPEC-013 US3, research D5)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.treasury.alerta_conciliacion import (
    AlertaConciliacion,
    EstadoAlerta,
    TipoAlerta,
)
from models.treasury.conciliacion import (
    Conciliacion,
    CruceConciliacion,
    CruceEstado,
)
from models.treasury.extracto_bancario import ExtractoBancario
from models.treasury.movimiento_bancario import MovimientoBancario

CERO = Decimal("0.0000")


async def _codigo_cuenta(db: AsyncSession, empresa_id: int, cuenta_id: int) -> str | None:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.id == cuenta_id
        )
    )
    return cuenta.code if cuenta else None


async def saldo_libros(
    db: AsyncSession, empresa_id: int, conciliacion: Conciliacion
) -> Decimal:
    codigo = await _codigo_cuenta(db, empresa_id, conciliacion.cuenta_id)
    if codigo is None:
        return CERO
    filas = (
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
                JournalEntry.estado == JournalEntryEstado.POSTED,
                JournalEntry.fecha >= conciliacion.fecha_inicio,
                JournalEntry.fecha <= conciliacion.fecha_fin,
            )
        )
    ).all()
    return sum((l.haber - l.debe for l in filas), CERO)


async def recalcular_saldos(
    db: AsyncSession, *, empresa_id: int, conciliacion: Conciliacion
) -> Conciliacion:
    """saldo_banco = extracto.saldo_final; saldo_libros = Σ(Haber−Debe) 572; diff exacta."""
    if conciliacion.extracto_id is not None:
        extracto = await db.scalar(
            select(ExtractoBancario).where(
                ExtractoBancario.empresa_id == empresa_id,
                ExtractoBancario.id == conciliacion.extracto_id,
            )
        )
        if extracto is not None:
            conciliacion.saldo_banco = extracto.saldo_final
    conciliacion.saldo_libros = await saldo_libros(db, empresa_id, conciliacion)
    conciliacion.diferencia = conciliacion.saldo_banco - conciliacion.saldo_libros
    await db.flush()
    return conciliacion


async def listar_pendientes(
    db: AsyncSession, empresa_id: int, conciliacion: Conciliacion
) -> dict:
    movs_cruce = select(CruceConciliacion.movimiento_id).where(
        CruceConciliacion.empresa_id == empresa_id,
        CruceConciliacion.estado == CruceEstado.confirmado,
    )
    apuntes_cruce = select(CruceConciliacion.apunte_id).where(
        CruceConciliacion.empresa_id == empresa_id,
        CruceConciliacion.estado == CruceEstado.confirmado,
    )
    movimientos = (
        await db.scalars(
            select(MovimientoBancario).where(
                MovimientoBancario.empresa_id == empresa_id,
                MovimientoBancario.id.not_in(movs_cruce),
            )
        )
    ).all()
    codigo = await _codigo_cuenta(db, empresa_id, conciliacion.cuenta_id)
    apuntes = []
    if codigo is not None:
        apuntes = list(
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
                        JournalEntryLine.id.not_in(apuntes_cruce),
                        JournalEntry.estado == JournalEntryEstado.POSTED,
                        JournalEntry.fecha >= conciliacion.fecha_inicio,
                        JournalEntry.fecha <= conciliacion.fecha_fin,
                    )
                )
            ).all()
        )
    return {
        "movimientos_sin_cruzar": [
            {
                "id": str(m.id),
                "fecha_operacion": m.fecha_operacion.isoformat(),
                "concepto": m.concepto,
                "importe": f"{m.importe:0.4f}",
                "signo": m.signo.value,
                "estado": m.estado.value,
            }
            for m in movimientos
        ],
        "apuntes_sin_extracto": [
            {
                "id": str(a.id),
                "cuenta": a.cuenta,
                "debe": f"{a.debe:0.4f}",
                "haber": f"{a.haber:0.4f}",
                "descripcion": a.descripcion,
            }
            for a in apuntes
        ],
    }


async def informe(
    db: AsyncSession, empresa_id: int, conciliacion: Conciliacion
) -> dict:
    await recalcular_saldos(db, empresa_id=empresa_id, conciliacion=conciliacion)
    pendientes = await listar_pendientes(db, empresa_id, conciliacion)
    alertas = (
        await db.scalars(
            select(AlertaConciliacion).where(
                AlertaConciliacion.empresa_id == empresa_id,
                AlertaConciliacion.conciliacion_id == conciliacion.id,
                AlertaConciliacion.estado == EstadoAlerta.abierta,
            )
        )
    ).all()
    return {
        "id": str(conciliacion.id),
        "cuenta_id": conciliacion.cuenta_id,
        "estado": conciliacion.estado.value,
        "saldo_banco": f"{conciliacion.saldo_banco:0.4f}",
        "saldo_libros": f"{conciliacion.saldo_libros:0.4f}",
        "diferencia": f"{conciliacion.diferencia:0.4f}",
        "pendientes": pendientes,
        "alertas": [
            {
                "id": str(a.id),
                "tipo": a.tipo.value,
                "descripcion": a.descripcion,
                "estado": a.estado.value,
            }
            for a in alertas
        ],
    }


async def generar_alertas(
    db: AsyncSession, empresa_id: int, conciliacion: Conciliacion
) -> list[AlertaConciliacion]:
    """Create alerts for unmatched movements/apuntes (informative, no asiento)."""
    pendientes = await listar_pendientes(db, empresa_id, conciliacion)
    existentes: set[tuple[str, uuid.UUID | None]] = {
        (a.tipo.value, a.movimiento_id)
        for a in (
            await db.scalars(
                select(AlertaConciliacion).where(
                    AlertaConciliacion.empresa_id == empresa_id,
                    AlertaConciliacion.conciliacion_id == conciliacion.id,
                    AlertaConciliacion.estado == EstadoAlerta.abierta,
                )
            )
        ).all()
    }
    creadas: list[AlertaConciliacion] = []
    for mov in pendientes["movimientos_sin_cruzar"]:
        clave = (TipoAlerta.movimiento_sin_apunte.value, uuid.UUID(mov["id"]))
        if clave in existentes:
            continue
        alerta = AlertaConciliacion(
            empresa_id=empresa_id,
            conciliacion_id=conciliacion.id,
            tipo=TipoAlerta.movimiento_sin_apunte,
            movimiento_id=uuid.UUID(mov["id"]),
            descripcion=f"Movimiento sin apunte: {mov['concepto']}",
        )
        db.add(alerta)
        creadas.append(alerta)
    if pendientes["apuntes_sin_extracto"]:
        clave_apunte: tuple[str, uuid.UUID | None] = (TipoAlerta.apunte_sin_extracto.value, None)
        if clave_apunte not in existentes:
            alerta = AlertaConciliacion(
                empresa_id=empresa_id,
                conciliacion_id=conciliacion.id,
                tipo=TipoAlerta.apunte_sin_extracto,
                descripcion=f"{len(pendientes['apuntes_sin_extracto'])} apunte(s) sin extracto",
            )
            db.add(alerta)
            creadas.append(alerta)
    await db.flush()
    return creadas
