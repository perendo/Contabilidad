"""Tests unitarios de cálculo de impuestos, recargo y criterio de caja (SPEC-007)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from models.invoice.factura import Factura
from services.invoicing.calculo_impuestos import (
    base_linea,
    calcular_linea,
    calcular_totales,
)
from services.invoicing.criterio_caja import (
    desmarcar_diferimiento,
    marcar_diferimiento,
)
from services.invoicing.errores import InvoicingError
from services.invoicing.recargo_equivalencia import TIPOS_VIGENTES, tipo_recargo_valido

COMUN = {
    "cantidad": "1",
    "precio_unitario": "100.0000",
    "porcentaje_descuento": "0",
    "tipo_iva": "21",
    "tipo_recargo": "0",
    "tipo_irpf": "0",
    "base_irpf": "0",
}


def _linea(**overrides) -> dict:
    return {**COMUN, **overrides}


def _code(exc: InvoicingError) -> str:
    return exc.code


def test_base_sin_descuento() -> None:
    assert base_linea(Decimal(1), Decimal(100), Decimal(0)) == Decimal(100)


def test_base_con_descuento_10() -> None:
    assert base_linea(Decimal(1), Decimal(100), Decimal(10)) == Decimal(90)


def test_calcular_linea_iva() -> None:
    res = calcular_linea(_linea())
    assert res["base"] == "100.0000"
    assert res["cuota_iva"] == "21.0000"
    assert res["cuota_recargo"] == "0.0000"
    assert res["cuota_irpf"] == "0.0000"


def test_calcular_linea_descuento_10() -> None:
    res = calcular_linea(_linea(porcentaje_descuento="10"))
    assert res["base"] == "90.0000"
    assert res["cuota_iva"] == "18.9000"


def test_calcular_linea_irpf_15() -> None:
    res = calcular_linea(_linea(tipo_irpf="15", base_irpf="100"))
    assert res["cuota_irpf"] == "15.0000"


def test_calcular_linea_recargo_520() -> None:
    res = calcular_linea(_linea(tipo_recargo="5.2"))
    assert res["cuota_recargo"] == "5.2000"


def test_redondeo_linea_a_linea() -> None:
    lineas = [calcular_linea(_linea(cantidad="1", precio_unitario="0.0150")) for _ in range(3)]
    assert all(l["cuota_iva"] == "0.0000" for l in lineas)
    totales = calcular_totales(lineas)
    assert totales["iva"] == "0.0000"


def test_totales_venta_con_irpf() -> None:
    lineas = [calcular_linea(_linea(tipo_irpf="15", base_irpf="100"))]
    totales = calcular_totales(lineas)
    assert totales["base"] == "100.0000"
    assert totales["iva"] == "21.0000"
    assert totales["irpf"] == "15.0000"
    assert totales["total"] == "106.0000"


def test_cantidad_invalida() -> None:
    with pytest.raises(InvoicingError) as exc:
        calcular_linea(_linea(cantidad="0"))
    assert _code(exc.value) == "cantidad_invalida"


def test_precio_invalido() -> None:
    with pytest.raises(InvoicingError) as exc:
        calcular_linea(_linea(precio_unitario="0"))
    assert _code(exc.value) == "precio_invalido"


def test_descuento_invalido() -> None:
    with pytest.raises(InvoicingError) as exc:
        calcular_linea(_linea(porcentaje_descuento="150"))
    assert _code(exc.value) == "descuento_invalido"


def test_base_irpf_invalida() -> None:
    with pytest.raises(InvoicingError) as exc:
        calcular_linea(_linea(base_irpf="-1"))
    assert _code(exc.value) == "base_irpf_invalida"


def test_total_negativo() -> None:
    lineas = [calcular_linea(_linea(tipo_irpf="200", base_irpf="100"))]
    with pytest.raises(InvoicingError) as exc:
        calcular_totales(lineas)
    assert _code(exc.value) == "total_negativo"


def test_tipos_recargo_vigentes() -> None:
    assert Decimal("5.20") in TIPOS_VIGENTES
    assert tipo_recargo_valido(Decimal("5.20"))
    assert tipo_recargo_valido(Decimal(0))
    assert not tipo_recargo_valido(Decimal("3.00"))


def test_criterio_caja_marca_y_desmarca() -> None:
    factura = Factura()
    marcar_diferimiento(factura)
    assert factura.regimen_caja is True
    assert factura.iva_devengado is False
    desmarcar_diferimiento(factura)
    assert factura.regimen_caja is False
    assert factura.iva_devengado is True