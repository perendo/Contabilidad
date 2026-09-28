"""Errores de dominio del modulo de cierres (SPEC-028).

El router `api/closing.py` los traduce a 404/409/422 con cuerpo
`{code, detail}` segun `contracts/api-contracts.md`.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ClosingError", "error"]


class ClosingError(Exception):
    """Error de negocio con codigo estable y status HTTP asociado."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 422,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}
        super().__init__(message)


def error(code: str, message: str, status_code: int = 422) -> ClosingError:
    """Atajo de construccion: `ClosingError` con el status ya resuelto."""
    return ClosingError(code, message, status_code)
