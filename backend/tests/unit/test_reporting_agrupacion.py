"""Tests unitarios de agrupacion y utilidades de reporting (SPEC-010 T008/T010/T011)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from services.reporting.agrupacion import (
    MASA_OTROS_CODIGO,
    agrupar,
    rango_matchea,
    resolver_masa,
)
from services.reporting.saldos import resultado_de_gestion


def _regla(codigo: str, nombre: str, ini: str, fin: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        agrupacion_codigo=codigo,
        agrupacion_nombre=nombre,
        cuenta_ini=ini,
        cuenta_fin=fin,
    )


def test_rango_prefijo() -> None:
    assert rango_matchea("2100", "21", None)
    assert not rango_matchea("2200", "21", None)


def test_rango_cerrado() -> None:
    assert rango_matchea("4300", "400", "4399")
    assert not rango_matchea("4400", "400", "4399")


def test_resolver_masa_configurada() -> None:
    reglas = [_regla("ANC", "Activo No Corriente", "21", "2199")]
    assert resolver_masa("2100", reglas) == ("ANC", "Activo No Corriente", True)


def test_resolver_masa_otros_sin_config() -> None:
    assert resolver_masa("2100", []) == (MASA_OTROS_CODIGO, "Otros", False)


def test_agrupar_acumula() -> None:
    reglas = [_regla("ACT", "Activo", "2", None)]
    masas, hay_otros = agrupar(
        {"2100": Decimal(100), "4300": Decimal(50)}, reglas, prefijos=("1", "2", "3", "4", "5")
    )
    assert hay_otros is True
    assert masas["ACT"]["importe"] == Decimal(100)
    assert masas["OTROS"]["importe"] == Decimal(50)


def test_resultado_de_gestion() -> None:
    netos = {
        "7000": Decimal(-5000),
        "6400": Decimal(2000),
        "6000": Decimal(1000),
        "4300": Decimal(8000),
    }
    assert resultado_de_gestion(netos) == Decimal(2000)