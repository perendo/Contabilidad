"""Errores de dominio del modulo de documentos adjuntos (SPEC-030)."""

from __future__ import annotations

from typing import Any


class DocumentoError(Exception):
    """Error de negocio con codigo estable y status HTTP asociado.

    El router lo traduce a ``404/409/422`` con cuerpo
    ``{"code", "detail", **extra}`` tal y como fija
    ``contracts/api-contracts.md``.

    El texto de un 404 es intencionadamente indistinguible del de un recurso
    inexistente ("El documento no existe o pertenece a otra empresa",
    research D14): un 403 confirmaria la existencia del recurso y permitiria
    enumerar la evidencia de otra empresa (FR-013, SC-003).
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


def error(
    code: str, message: str, status_code: int = 422
) -> DocumentoError:
    return DocumentoError(code, message, status_code)
