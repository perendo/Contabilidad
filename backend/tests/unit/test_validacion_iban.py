"""Tests SPEC-008 Foundational (T012): validación IBAN ISO 13616."""

from __future__ import annotations

from services.thirdparty.bancos import normalizar_iban, validar_iban


def test_iban_espanol_valido() -> None:
    assert validar_iban("ES9121000418450200051332") is True


def test_iban_invalido() -> None:
    assert validar_iban("ES9121000418450200051333") is False
    assert validar_iban("ES91") is False
    assert validar_iban("") is False


def test_iban_otro_pais() -> None:
    assert validar_iban("DE89370400440532013000") is True


def test_normalizacion() -> None:
    assert normalizar_iban(" es91 2100-0418 4502 0005 1332 ") == "ES9121000418450200051332"
