"""Errores de dominio de la exportacion integral (SPEC-029).

`services.export.errores` los traduce `api/export.py` a 404/409/422 con cuerpo
`{code, detail}` segun `contracts/api-contracts.md`.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ExportError", "error"]


class ExportError(Exception):
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


def error(code: str, message: str, status_code: int = 422) -> ExportError:
    """Atajo de construccion: `ExportError` con el status ya resuelto."""
    return ExportError(code, message, status_code)
