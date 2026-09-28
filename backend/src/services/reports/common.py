"""Aggregation helpers for derived reports (SPEC-004 T004).

All monetary aggregation uses :class:`~decimal.Decimal` (never ``float``);
presentation values are quantized to 4 decimals.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CUATRO = Decimal("0.0000")


def rollup_code(code: str, level: int) -> str:
    """Aggregate key for a plan code at the requested depth level.

    Level ``n`` keeps the first ``n`` digits; a code shorter than the level
    aggregates under itself (never errors on deeper-than-plan levels).
    """
    if level <= 0:
        raise ValueError("level debe ser >= 1")
    return code[:level] if len(code) > level else code


def cuantizar(importe: Decimal | str | int) -> Decimal:
    """Quantize a monetary value to exactly 4 decimals (half up)."""
    return Decimal(str(importe)).quantize(CUATRO, rounding=ROUND_HALF_UP)


def fmt(importe: Decimal) -> str:
    """Uniform 4-decimal string presentation for report payloads."""
    return f"{cuantizar(importe):0.4f}"
