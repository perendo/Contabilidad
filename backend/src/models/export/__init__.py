"""Modelos de la exportacion integral (SPEC-029).

`ConfigSii` (opcional, US3), `Exportacion` (cabecera correlativa e inmutable),
`ManifiestoExportacion` + `ManifiestoBloque` (inventario de bloques, append-only)
y `BlobExportacion` (binario BYTEA inmutable del ZIP). Todos con
`UNIQUE(empresa_id, id)` y `empresa_id` en indices y FKs compuestas
(constitucion III).
"""

from models.export.blob_exportacion import BlobExportacion
from models.export.config_sii import ConfigSii
from models.export.exportacion import (
    ESTADOS_FINALES,
    LIMITE_BYTES,
    EstadoExportacion,
    Exportacion,
    TipoExportacion,
)
from models.export.manifiesto import (
    FORMATO_VERSION,
    ManifiestoBloque,
    ManifiestoExportacion,
)

__all__ = [
    "ESTADOS_FINALES",
    "FORMATO_VERSION",
    "LIMITE_BYTES",
    "BlobExportacion",
    "ConfigSii",
    "EstadoExportacion",
    "Exportacion",
    "ManifiestoBloque",
    "ManifiestoExportacion",
    "TipoExportacion",
]
