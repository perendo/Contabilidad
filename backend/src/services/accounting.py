"""Minimal accounting helpers used by treasury asientos (SPEC-020).

Only what US1 requires: strict balance validation (constitución I) and the
collection asiento template (Debe banco, Haber 430).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from models.acct.journal import (
    JournalEntry,
    JournalEntryLine,
    JournalEntryTipo,
)

CUENTA_CLIENTES = "430"


class BalanceError(Exception):
    def __init__(self, debe: Decimal, haber: Decimal) -> None:
        self.debe = debe
        self.haber = haber
        super().__init__(f"asiento desbalanceado: Debe {debe} != Haber {haber}")


def verificar_balance(lines: list[JournalEntryLine]) -> None:
    """Raise BalanceError unless SUM(debe) == SUM(haber) exactly (Decimal)."""
    debe = sum((line.debe for line in lines), Decimal(0))
    haber = sum((line.haber for line in lines), Decimal(0))
    if debe != haber:
        raise BalanceError(debe, haber)


def construir_asiento_cobro(
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    importe: Decimal,
    cuenta_banco: str,
    concepto: str,
) -> tuple[JournalEntry, list[JournalEntryLine]]:
    """Collection asiento: Debe cuenta_banco (importe) | Haber 430 (importe)."""
    importe = Decimal(importe)
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=JournalEntryTipo.COBRO,
        concepto=concepto,
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    lines = [
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=cuenta_banco,
            debe=importe,
            haber=Decimal(0),
            descripcion=None,
        ),
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=CUENTA_CLIENTES,
            debe=Decimal(0),
            haber=importe,
            descripcion=None,
        ),
    ]
    verificar_balance(lines)
    return asiento, lines