"""Tests SPEC-008 Foundational (T011): validación NIF/CIF/NIE."""

from __future__ import annotations

from services.thirdparty.validacion_nif import normalizar_nif, validar_nif


def test_dni_valido_e_invalido() -> None:
    assert validar_nif("12345678Z") is True
    assert validar_nif("12345678A") is False
    assert validar_nif("1234567Z") is False


def test_nie_valido() -> None:
    assert validar_nif("X1234567L") is True
    assert validar_nif("Y1234567X") is True
    assert validar_nif("X1234567A") is False


def test_cif_valido_e_invalido() -> None:
    assert validar_nif("A12345674") is True
    assert validar_nif("A12345670") is False
    assert validar_nif("B00000001") is False


def test_normalizacion() -> None:
    assert normalizar_nif(" 12345678-z ") == "12345678Z"
    assert validar_nif(" 12345678-z ") is True


def test_vacio_invalido() -> None:
    assert validar_nif("") is False
    assert validar_nif("ABC") is False
