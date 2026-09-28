"""Cálculo de impuestos (SPEC-007 T009): base, IVA, recargo e IRPF en Decimal.

Redondeo **línea a línea** a 2 decimales de las cuotas (práctica fiscal LIVA);
los totales se agregan y se cuantizan a 4 decimales para ``NUMERIC(18,4)``.
``float`` prohibido (constitución). ``calcular_linea`` rechaza cantidades,
precios y descuentos inválidos y bases negativas.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from services.invoicing.errores import error
from services.journal.money import as_decimal, tiene_mas_de_4_decimales

CUANTUM_2 = Decimal("0.01")


def _quantum2(value: Decimal) -> Decimal:
    return value.quantize(CUANTUM_2, rounding=ROUND_HALF_EVEN)


def _cantidad(campo: str, valor: Any) -> Decimal:
    texto = str(valor)
    if tiene_mas_de_4_decimales(texto):
        raise error("precision_invalida", f"{campo}: más de 4 decimales")
    return Decimal(texto)


def _porcentaje(campo: str, valor: Any) -> Decimal:
    texto = str(valor)
    if tiene_mas_de_4_decimales(texto):
        raise error("precision_invalida", f"{campo}: más de 4 decimales")
    return Decimal(texto)


def base_linea(
    cantidad: Decimal, precio_unitario: Decimal, porcentaje_descuento: Decimal
) -> Decimal:
    base = cantidad * precio_unitario
    if porcentaje_descuento:
        base = base * (1 - porcentaje_descuento / 100)
    return as_decimal(base)


def calcular_linea(linea: dict[str, Any]) -> dict[str, str]:
    """Calcula base y cuotas de una línea (redondeo línea a línea a 2 dec.)."""
    cantidad = _cantidad("cantidad", linea["cantidad"])
    precio = _cantidad("precio_unitario", linea["precio_unitario"])
    descuento = _porcentaje("porcentaje_descuento", linea.get("porcentaje_descuento") or 0)
    tipo_iva = _porcentaje("tipo_iva", linea.get("tipo_iva") or 0)
    tipo_recargo = _porcentaje("tipo_recargo", linea.get("tipo_recargo") or 0)
    tipo_irpf = _porcentaje("tipo_irpf", linea.get("tipo_irpf") or 0)
    base_irpf = _cantidad("base_irpf", linea.get("base_irpf") or 0)

    if cantidad <= 0:
        raise error("cantidad_invalida", "La cantidad debe ser mayor que 0")
    if precio <= 0:
        raise error("precio_invalido", "El precio unitario debe ser mayor que 0")
    if descuento < 0 or descuento > 100:
        raise error("descuento_invalido", "El descuento debe estar entre 0 y 100")
    if base_irpf < 0:
        raise error("base_irpf_invalida", "La base del IRPF no puede ser negativa")

    base = base_linea(cantidad, precio, descuento)
    if base < 0:
        raise error("base_negativa", "La base de la línea no puede ser negativa")

    cuota_iva = _quantum2(base * tipo_iva / 100)
    cuota_recargo = _quantum2(base * tipo_recargo / 100)
    cuota_irpf = _quantum2(base_irpf * tipo_irpf / 100)

    return {
        "base": f"{as_decimal(base):0.4f}",
        "cuota_iva": f"{as_decimal(cuota_iva):0.4f}",
        "cuota_recargo": f"{as_decimal(cuota_recargo):0.4f}",
        "cuota_irpf": f"{as_decimal(cuota_irpf):0.4f}",
    }


def calcular_totales(lineas: list[dict[str, Any]]) -> dict[str, str]:
    """Agrega en Decimal base/IVA/recargo/IRPF y total de la factura."""
    base = sum((Decimal(str(l["base"])) for l in lineas), Decimal(0))
    iva = sum((Decimal(str(l["cuota_iva"])) for l in lineas), Decimal(0))
    recargo = sum((Decimal(str(l["cuota_recargo"])) for l in lineas), Decimal(0))
    irpf = sum((Decimal(str(l["cuota_irpf"])) for l in lineas), Decimal(0))
    total = base + iva + recargo - irpf
    if total < 0:
        raise error("total_negativo", "El importe total de la factura no puede ser negativo")
    return {
        "base": f"{as_decimal(base):0.4f}",
        "iva": f"{as_decimal(iva):0.4f}",
        "recargo": f"{as_decimal(recargo):0.4f}",
        "irpf": f"{as_decimal(irpf):0.4f}",
        "total": f"{as_decimal(total):0.4f}",
    }