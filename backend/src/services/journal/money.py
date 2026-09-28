"""Money precision utilities (SPEC-002 T004).

Importes are always Decimal; canonical representation is 4 decimal places with
ROUND_HALF_EVEN. `float` is forbidden for monetary amounts.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

QUANTUM = Decimal("0.0001")


def as_decimal(value: str | int | Decimal) -> Decimal:
    """Normalize to 4 decimal places with ROUND_HALF_EVEN (never float)."""
    return Decimal(str(value)).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)


def as_decimal_str(value: str | int | Decimal) -> str:
    return f"{as_decimal(value):0.4f}"


def tiene_mas_de_4_decimales(value: str | int | Decimal) -> bool:
    dec = Decimal(str(value))
    exponente = dec.as_tuple().exponent
    if not isinstance(exponente, int):
        return True
    return exponente < -4