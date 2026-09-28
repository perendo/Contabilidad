"""Errores del modulo ngo (SPEC-019): excepcion unica con `code` + mensaje."""

from __future__ import annotations


class NgoError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def error(code: str, message: str) -> NgoError:
    return NgoError(code, message)