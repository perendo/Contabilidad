"""Saldos de tesoreria: diario (SPEC-002) y conciliacion (SPEC-013).

research.md D1 fija la precedencia del `saldo_inicial`:

1. **Conciliacion bancaria** (SPEC-013): el `saldo_banco` del ultimo extracto
   de una cuenta del grupo 5 anterior al inicio de la proyeccion.
2. **Balance del motor de asientos** (SPEC-002): `S(debe - haber)` de las
   cuentas del grupo 5 con fecha anterior al inicio de la proyeccion, excluyendo
   el asiento de cierre del ejercicio (que solo cuadra artificialmente).

FR-005/D5 reutilizan estas lecturas para cruzar el saldo final del EFE con el
saldo conciliado. Solo lectura: nunca se modifica el diario (constitucion II).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.treasury.conciliacion import Conciliacion
from services.cashflow.utils import c4, es_cuenta_tesoreria

__all__ = [
    "ORIGEN_CONCILIACION",
    "ORIGEN_DIARIO",
    "saldo_conciliacion",
    "saldo_tesoreria",
    "saldo_tesoreria_inicial",
]

ORIGEN_CONCILIACION = "conciliacion"
ORIGEN_DIARIO = "diario"


async def saldo_tesoreria(
    db: AsyncSession,
    *,
    empresa_id: int,
    hasta_fecha: date,
    solo_apertura: bool = False,
) -> Decimal:
    """Saldo del grupo 5 acumulado hasta `hasta_fecha` (exclusive), a 4 decimales.

    `solo_apertura = True` restringe el calculo a los asientos `OPENING`, que es
    el saldo de tesoreria con el que arranca el ejercicio (el resto de la
    variacion son los flujos del bloque del EFE).
    """
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == hasta_fecha.year
        )
    )
    consulta = (
        select(JournalEntryLine.cuenta, JournalEntryLine.debe, JournalEntryLine.haber)
        .join(
            JournalEntry,
            (JournalEntry.id == JournalEntryLine.journal_entry_id)
            & (JournalEntry.empresa_id == JournalEntryLine.empresa_id),
        )
        .where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.estado == JournalEntryEstado.POSTED,
            JournalEntry.fecha < hasta_fecha,
        )
    )
    if solo_apertura:
        consulta = consulta.where(JournalEntry.tipo == JournalEntryTipo.OPENING)
    if fy is not None and fy.cierre_entry_id is not None:
        # El cierre salda todas las cuentas: contaminaria el saldo real.
        consulta = consulta.where(JournalEntry.id != fy.cierre_entry_id)

    total = Decimal(0)
    for codigo, debe, haber in (await db.execute(consulta)).all():
        if es_cuenta_tesoreria(codigo):
            total += Decimal(str(debe or 0)) - Decimal(str(haber or 0))
    return c4(total)


async def saldo_conciliacion(
    db: AsyncSession, *, empresa_id: int, hasta_fecha: date
) -> Decimal | None:
    """`saldo_banco` del ultimo extracto conciliado anterior a `hasta_fecha`.

    `None` cuando la empresa no ha conciliado ninguna cuenta de tesoreria: en
    ese caso FR-005/D5 no tienen contra que cruzar y el informe no se marca
    como `sin_conciliar` (no es una diferencia, es una ausencia de dato).
    """
    ultima = await db.scalar(
        select(Conciliacion)
        .where(
            Conciliacion.empresa_id == empresa_id,
            Conciliacion.fecha_fin < hasta_fecha,
        )
        .order_by(Conciliacion.fecha_fin.desc(), Conciliacion.ejercicio.desc())
        .limit(1)
    )
    if ultima is None:
        return None
    return c4(ultima.saldo_banco)


async def saldo_tesoreria_inicial(
    db: AsyncSession, *, empresa_id: int, desde_fecha: date
) -> tuple[Decimal, str]:
    """Saldo inicial de la proyeccion y su origen (research D1).

    Devuelve `(saldo, "conciliacion" | "diario")` para que la cabecera de la
    prevision guarde la trazabilidad de la fuente (D1/D9).
    """
    conciliado = await saldo_conciliacion(
        db, empresa_id=empresa_id, hasta_fecha=desde_fecha
    )
    if conciliado is not None:
        return conciliado, ORIGEN_CONCILIACION
    saldo = await saldo_tesoreria(db, empresa_id=empresa_id, hasta_fecha=desde_fecha)
    return saldo, ORIGEN_DIARIO
