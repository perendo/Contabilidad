"""Criterio de caja (SPEC-007 FR-011 / T011).

En régimen de caja la factura se emite con el IVA íntegro pero **diferido**:
``regimen_caja = true`` e ``iva_devengado = false``; el saldo queda en
477/472 pendiente de liquidación y SPEC-012 (libros de IVA) gestiona el
devengo al cobro/pago. Esta feature solo marca el diferimiento.
"""

from __future__ import annotations

from models.invoice.factura import Factura


def marcar_diferimiento(factura: Factura) -> None:
    """Marca la factura como régimen de caja con IVA diferido."""
    factura.regimen_caja = True
    factura.iva_devengado = False


def desmarcar_diferimiento(factura: Factura) -> None:
    factura.regimen_caja = False
    factura.iva_devengado = True