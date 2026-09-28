"""Tests SPEC-005 Foundational (T008): parseo de importes a Decimal."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.importexport.parseador import ParseError, parse_decimal


def test_coma_decimal_y_miles() -> None:
    assert parse_decimal("1.250,50") == Decimal("1250.50")


def test_punto_decimal() -> None:
    assert parse_decimal("1250.50") == Decimal("1250.50")


def test_entero_y_vacio() -> None:
    assert parse_decimal("1250") == Decimal(1250)
    assert parse_decimal("") == Decimal(0)
    assert parse_decimal("   ") == Decimal(0)


def test_miles_con_coma_decimal() -> None:
    assert parse_decimal("12.345,67") == Decimal("12345.67")


def test_invalido_lanza_error() -> None:
    with pytest.raises(ParseError) as exc:
        parse_decimal("abc")
    assert exc.value.code == "importe_invalido"


def test_negativo_rechazado() -> None:
    with pytest.raises(ParseError) as exc:
        parse_decimal("-100")
    assert exc.value.code == "importe_invalido"
