"""Unit tests SPEC-002 T012: balance estricto y precisión (FR-002/FR-006)."""

from __future__ import annotations

from decimal import Decimal

from services.journal.money import as_decimal, tiene_mas_de_4_decimales


async def test_normalizacion_canonica_4_decimales():
    assert as_decimal("100") == Decimal("100.0000")
    assert as_decimal("100.1234") == Decimal("100.1234")
    assert as_decimal("1.99995") == Decimal("2.0000")


async def test_deteccion_precision_excesiva():
    assert tiene_mas_de_4_decimales("100.12345")
    assert not tiene_mas_de_4_decimales("100.1234")
    assert not tiene_mas_de_4_decimales("100")


async def test_desbalanceado_422(journal_api):
    c = journal_api.cuentas["a"]
    respuesta = journal_api.crear(
        lineas=[
            {"account_id": c["4300"], "debit": "100.0000", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "90.0000"},
        ]
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "desbalanceado"


async def test_equilibrado_aceptado_con_suma_exacta(journal_api):
    respuesta = journal_api.crear()
    assert respuesta.status_code == 201
    body = respuesta.json()
    assert body["suma_debe"] == "100.0000"
    assert body["suma_haber"] == "100.0000"
    assert Decimal(body["suma_debe"]) == Decimal(body["suma_haber"])


async def test_precision_excesiva_linea_422(journal_api):
    c = journal_api.cuentas["a"]
    respuesta = journal_api.crear(
        lineas=[
            {"account_id": c["4300"], "debit": "100.12345", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "100.12345"},
        ]
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "precision_invalida"


async def test_linea_malformada_solo_debe_o_haber(journal_api):
    c = journal_api.cuentas["a"]
    respuesta = journal_api.crear(
        lineas=[
            {"account_id": c["4300"], "debit": "100", "credit": "10"},
            {"account_id": c["5720"], "debit": "0", "credit": "110"},
        ]
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "linea_invalida"


async def test_importes_negativos_rechazados(journal_api):
    c = journal_api.cuentas["a"]
    respuesta = journal_api.crear(
        lineas=[
            {"account_id": c["4300"], "debit": "100", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "-100"},
        ]
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "importe_negativo"


async def test_una_linea_422(journal_api):
    c = journal_api.cuentas["a"]
    respuesta = journal_api.crear(
        lineas=[{"account_id": c["4300"], "debit": "100", "credit": "0"}]
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "lineas_insuficientes"