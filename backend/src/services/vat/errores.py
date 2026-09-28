"""Error compartido del modulo de IVA/modelos fiscales (SPEC-012)."""

from __future__ import annotations


class VatError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def error(code: str, message: str) -> VatError:
    return VatError(code, message)