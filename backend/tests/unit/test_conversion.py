"""Conversión y redondeo de divisa a moneda funcional (SPEC-016 T012).

`convertir` usa Decimal con ROUND_HALF_EVEN a 4 decimales; nunca float
(constitución I). El remanente se resuelve por la línea de redondeo del
servicio de asiento, no en esta función pura.
"""

from __future__ import annotations

from decimal import Decimal

from services.forex.conversion import convertir, tiene_mas_de_4


def test_cuatro_decimales_exacto() -> None:
    assert convertir(Decimal("1000.0000"), Decimal("1.08500000")) == Decimal("1085.0000")


def test_escala_ocho_decimales_ratio() -> None:
    assert convertir(Decimal("3333.0000"), Decimal("0.33333333")) == Decimal("1111.0000")
    assert convertir(Decimal("9999999999.9999"), Decimal("0.33333333")) == Decimal(
        "3333333300.0000"
    )


def test_round_half_even_sube() -> None:
    # 123.45755: el 5º decimal (5) es la mitad exacta -> sube al par
    assert convertir(Decimal("123.45755"), Decimal("1.00000000")) == Decimal("123.4576")


def test_round_half_even_baja() -> None:
    # 123.45745: mitad exacta -> se mantiene el par (4)
    assert convertir(Decimal("123.45745"), Decimal("1.00000000")) == Decimal("123.4574")


def test_importe_extremo_ratio_grande() -> None:
    assert convertir(Decimal("9999999999.9999"), Decimal("2.00000000")) == Decimal(
        "19999999999.9998"
    )


def test_ratios_muchos_decimales_sin_desequilibrio() -> None:
    # El resultado SIEMPRE tiene 4 decimales (quantized)
    value = convertir(Decimal("1000.0007"), Decimal("1.00000001"))
    assert value.as_tuple().exponent == -4


def test_tiene_mas_de_4_detecta_precision() -> None:
    assert tiene_mas_de_4("1.00001")
    assert not tiene_mas_de_4("1.0001")
    assert not tiene_mas_de_4("1")