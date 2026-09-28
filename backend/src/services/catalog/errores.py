"""Domain errors for the versioned catalogue (SPEC-025)."""

from __future__ import annotations

from typing import Any


class CatalogoError(Exception):
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
