"""Tests SPEC-013 US1 (T013/T014): parser norma 43/19 y CSV."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from services.reconciliation.parsers import (
    LayoutError,
    parse_csv_normalizado,
    parse_norma_43,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _leer(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


def test_parser_norma_43_valido() -> None:
    dto = parse_norma_43(_leer("extracto_43_19_valido.txt"))
    assert dto.cuenta == "5720"
    assert dto.saldo_inicial == Decimal("0.0000")
    assert dto.saldo_final == Decimal("1105.0000")
    assert len(dto.movimientos) == 3
    assert [m.signo for m in dto.movimientos] == ["D", "D", "H"]
    assert dto.movimientos[0].importe == Decimal("500.0000")
    assert dto.movimientos[2].importe == Decimal("1805.0000")
    assert dto.fecha_inicio is not None


def test_parser_norma_43_malformado() -> None:
    with pytest.raises(LayoutError) as exc:
        parse_norma_43(_leer("extracto_43_19_malformado.txt"))
    assert exc.value.code == "layout_invalido"
    assert exc.value.registro >= 1


def test_parser_csv_normalizado() -> None:
    dto = parse_csv_normalizado(_leer("extracto_csv_normalizado.csv"))
    assert len(dto.movimientos) == 3
    assert dto.movimientos[0].signo == "D"
    assert dto.movimientos[2].importe == Decimal("1805.0000")
    neto = sum(
        (m.importe if m.signo == "H" else -m.importe for m in dto.movimientos),
        Decimal(0),
    )
    assert neto == Decimal("1105.0000")


def test_parser_csv_cabecera_incompleta() -> None:
    with pytest.raises(LayoutError):
        parse_csv_normalizado(b"a;b;c\n1;2;3\n")
