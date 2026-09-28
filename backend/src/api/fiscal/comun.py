"""Mapeo comun de errores del modulo fiscal a HTTP (SPEC-012)."""

from __future__ import annotations

from fastapi import HTTPException, status

from services.vat.errores import VatError

CODIGOS_404 = {
    "factura_no_encontrada",
    "exportacion_no_encontrada",
    "diferido_no_encontrado",
}
CODIGOS_409 = {
    "ejercicio_no_definido",
    "periodo_fuera_de_rango",
    "sii_no_habilitado",
    "modelo_no_preparado",
    "tipo_libro_invalido",
    "no_criterio_caja",
    "periodo_exportado",
}


def http_error(exc: VatError) -> HTTPException:
    detalle = {"code": exc.code, "detail": str(exc)}
    if exc.code in CODIGOS_404:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detalle)
    if exc.code in CODIGOS_409:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detalle
    )