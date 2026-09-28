"""Excepciones de negocio del módulo inmovilizado (SPEC-014).

Cada error lleva un ``code`` estable (contrato API) y un mensaje legible; el
status HTTP por defecto es 422 (validación de negocio). El mapeo a ``HTTPException``
se hace en la capa API (``api/inmovilizado/activos.py`` / ``amortizaciones.py``).
"""

from __future__ import annotations


class InmovilizadoError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def error(code: str, mensaje: str, status_code: int = 422) -> InmovilizadoError:
    return InmovilizadoError(code, mensaje, status_code)