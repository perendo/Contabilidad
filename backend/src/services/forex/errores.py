"""Domain errors del módulo forex (SPEC-016)."""

from __future__ import annotations


class ForexError(Exception):
    """Error de dominio de multi-divisa con ``code`` estable para la API."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)