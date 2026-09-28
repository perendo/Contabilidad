from __future__ import annotations


class FiscalISError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def error(code: str, message: str) -> FiscalISError:
    return FiscalISError(code, message)
