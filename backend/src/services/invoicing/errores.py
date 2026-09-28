"""Error compartido del módulo de facturación (SPEC-007).

Patrón de la casa: excepción con ``code`` + mensaje; la capa API lo mapea a
HTTP (404/400/409/422) según convención de contrato.
"""

from __future__ import annotations


class InvoicingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def error(code: str, message: str) -> InvoicingError:
    return InvoicingError(code, message)