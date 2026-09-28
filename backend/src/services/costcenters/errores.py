"""Domain errors del módulo costcenters (SPEC-017)."""

from __future__ import annotations


class CostcenterError(Exception):
    """Error de dominio de centros de coste con ``code`` estable para la API."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)