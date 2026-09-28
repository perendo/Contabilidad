"""Conversión divisa -> moneda funcional (SPEC-016 US1).

Importes en divisa y funcional son siempre Decimal; el equivalente funcional se
redondea a 4 decimales (ROUND_HALF_EVEN) línea a línea. El remanente de
redondeo nunca desequilibra el asiento: se imputa a una línea de redondeo de la
cuenta 6680/7690 como cierre del cuadre (constitución I).
"""

from __future__ import annotations

from decimal import Decimal

from services.journal.money import as_decimal, tiene_mas_de_4_decimales

CUATRO_DEC = Decimal("0.0001")


def convertir(importe_divisa: Decimal, ratio: Decimal) -> Decimal:
    """Equivalente en moneda funcional a 4 decimales (ROUND_HALF_EVEN)."""
    return as_decimal(importe_divisa * ratio)


def tiene_mas_de_4(importe_divisa: str | int | Decimal) -> bool:
    return tiene_mas_de_4_decimales(importe_divisa)