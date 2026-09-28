"""Recargo de equivalencia (SPEC-007 FR-010 / T010).

La cuota de recargo se calcula por línea (``base * tipo_recargo``) y se
contabiliza en cuenta separada del IVA (477/472 recargo). La configuración de
la empresa (régimen de recargo) vive en la config fiscal de SPEC-001; esta
feature consume el ``tipo_recargo`` declarado por línea. Tipos vigentes:
5,20 % general, 1,40 % reducido/superreducido y 0,50 % productos.
"""

from __future__ import annotations

from decimal import Decimal

TIPOS_VIGENTES = (Decimal("0.00"), Decimal("0.50"), Decimal("1.40"), Decimal("5.20"))
TIPOS_RECARGO_VENTA = ("4772",)
TIPOS_RECARGO_COMPRA = ("4722",)


def tipo_recargo_valido(tipo: Decimal) -> bool:
    return tipo in TIPOS_VIGENTES


def cuota_recargo(base: Decimal, tipo: Decimal) -> Decimal:
    """Cuota separada = base * tipo_recargo (idéntica regla que el IVA)."""
    from decimal import ROUND_HALF_EVEN

    return (base * tipo / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)