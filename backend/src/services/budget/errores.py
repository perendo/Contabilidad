"""Errores de dominio del modulo de presupuestos (SPEC-026)."""

from __future__ import annotations

from typing import Any


class PresupuestoError(Exception):
    """Error de negocio con codigo estable y status HTTP asociado.

    El router lo traduce a ``422/409/404`` con cuerpo ``{code, detail}`` tal y
    como fijan los contratos de ``contracts/api-contracts.md``.
    """

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


def error(code: str, message: str, status_code: int = 422) -> PresupuestoError:
    return PresupuestoError(code, message, status_code)
