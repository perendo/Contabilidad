"""Servicios de la exportacion integral del tenant (SPEC-029).

- `bloques`: catalogo de los 17 bloques de datos exportables (FR-004).
- `recopilar`: consultas paginadas con filtro de empresa y de ejercicio.
- `serializacion`: `Decimal`/fecha/UUID a JSON sin `float` (research D7).
- `manifiesto`: `manifest.json` interior y digest del contenido.
- `zip_generator`: ZIP determinista y huella del binario.
- `persistir`: cabecera correlativa + blob + manifiesto + audit en ACID.
- `verificar`: verificacion de integridad (US2).
- `sii`: datos normalizados para el SII de la AEAT (US3, opcional).
- `errores`: `ExportError` con codigo estable y status HTTP.
"""

from services.export.errores import ExportError, error

__all__ = ["ExportError", "error"]
