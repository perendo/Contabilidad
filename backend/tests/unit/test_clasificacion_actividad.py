"""Clasificacion de cuentas por bloque de actividad del EFE (T022, US2/D4).

Grupos 6/7 y tesoreria -> operativa; grupo 2 (y 8) -> inversion; grupos 1/9/16/17
-> financiacion. Las cuentas sin regla caen en operativa (bloque por defecto
del PGC) para que ningun asiento se quede fuera del informe.
"""

from __future__ import annotations

import pytest

from services.cashflow.clasificacion_actividad import (
    clasificar_bloque,
    es_bloque,
    grupos_de,
)

# research D4: operativa = grupos 6/7/tesoreria; inversion = grupo 2; financiacion
# = grupos 1/9 y deudas 16/17.
OPERATIVAS = [
    "5720", "5700", "572", "570",  # tesoreria
    "6000", "6210", "6400", "6810", "6300",  # grupo 6
    "7000", "7050", "7900",  # grupo 7
    "4720", "4750", "4300", "4100", "4000",  # tesoreria indirecta / corrientes
]
INVERSIONES = ["2160", "2100", "2170", "2500", "2810", "2300", "8000", "8200"]
FINANCIACIONES = ["1000", "1100", "1500", "1600", "1700", "1701", "9000", "9400", "9999"]


@pytest.mark.parametrize("codigo", OPERATIVAS)
def test_grupos_operativos(codigo):
    assert clasificar_bloque(codigo) == "operativa"


@pytest.mark.parametrize("codigo", INVERSIONES)
def test_grupos_de_inversion(codigo):
    assert clasificar_bloque(codigo) == "inversion"


@pytest.mark.parametrize("codigo", FINANCIACIONES)
def test_grupos_de_financiacion(codigo):
    assert clasificar_bloque(codigo) == "financiacion"


@pytest.mark.parametrize("codigo", [None, "", "  ", "ABC", "3000", "4999", "410"])
def test_cuentas_sin_regla_caen_en_operativa(codigo):
    """Ningun asiento se queda fuera del informe por falta de regla."""
    assert clasificar_bloque(codigo) == "operativa"


def test_grupos_de_extrae_dos_digitos():
    assert grupos_de("5720") == "57"
    assert grupos_de("572") == "57"
    assert grupos_de("57") == "57"
    assert grupos_de("5") == "5"
    assert grupos_de("1600") == "16"
    assert grupos_de("1") == "1"
    assert grupos_de(None) == ""


def test_es_bloque_valido():
    assert es_bloque("operativa")
    assert es_bloque("inversion")
    assert es_bloque("financiacion")
    assert not es_bloque("operativo")
    assert not es_bloque("")
