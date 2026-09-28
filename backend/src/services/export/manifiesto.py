"""Construccion del `manifest.json` interior del ZIP (SPEC-029 T019, research D6).

El manifiesto lleva el inventario de bloques con su conteo y huella, la version
del formato, la fecha de generacion en UTC y el `tenant_id` que **debe** coincidir
con el `empresa_id` que verifica (aislamiento, constitution III).

Sobre la huella: un fichero no puede contener su propio SHA-256, asi que el
manifesto interior declara `sha256_contenido`, el digest del contenido de los
bloques (`ruta|sha256` por bloque, en orden). La huella del **binario completo**
del ZIP vive en `Exportacion.sha256`, `BlobExportacion.sha256` y
`ManifiestoExportacion.sha256_fichero`, y la API la devuelve como
`sha256` / `manifiesto.sha256_fichero` (desvio documentado en el tasks.md).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from models.export.manifiesto import FORMATO_VERSION
from services.export.recopilar import BloqueRecopilado
from services.export.serializacion import iso_utc

__all__ = [
    "FORMATO_VERSION",
    "LineaManifiesto",
    "contenido_digest",
    "generar_manifiesto",
    "lineas_manifiesto",
]


class LineaManifiesto(dict):
    """Linea de bloque del manifiesto (`ManifiestoBloque` en la base de datos)."""


def lineas_manifiesto(bloques: list[BloqueRecopilado]) -> list[LineaManifiesto]:
    """Lineas del inventario en el orden de escritura de los bloques."""
    lineas: list[LineaManifiesto] = []
    for recopilado in bloques:
        lineas.append(
            LineaManifiesto(
                bloque=recopilado.bloque.nombre,
                fichero=recopilado.bloque.fichero,
                descripcion=recopilado.bloque.descripcion,
                entidades_exportadas=recopilado.bloque.entidades,
                conteo_registros=recopilado.conteo_registros,
                sha256=recopilado.sha256,
                fecha_min=recopilado.fecha_min,
                fecha_max=recopilado.fecha_max,
                ejercicio_min=recopilado.ejercicio_min,
                ejercicio_max=recopilado.ejercicio_max,
            )
        )
    return lineas


def generar_manifiesto(
    empresa_id: int,
    bloques: list[BloqueRecopilado],
    *,
    ejercicio_desde: int | None,
    ejercicio_hasta: int | None,
    fecha_generacion: datetime,
    sha256_contenido: str,
    numero_exportacion: int | None = None,
    tipo: str = "INTEGRAL",
) -> dict[str, Any]:
    """Dict del `manifest.json` interior, en el orden de `export-layout.md` 2."""
    manifiesto: dict[str, Any] = {
        "formato_version": FORMATO_VERSION,
        "fecha_generacion": iso_utc(fecha_generacion),
        "tenant_id": empresa_id,
        "empresa_id": empresa_id,
        "tipo": tipo,
        "numero_exportacion": numero_exportacion,
        "ejercicio_desde": ejercicio_desde,
        "ejercicio_hasta": ejercicio_hasta,
        "n_bloques": len(bloques),
        "bloques": [dict(linea) for linea in lineas_manifiesto(bloques)],
        "sha256_contenido": sha256_contenido,
    }
    return manifiesto


def contenido_digest(hashes: dict[str, str]) -> str:
    """SHA-256 canonico del contenido: `ruta|sha256` de cada bloque, en orden.

    Es lo que permite verificar la integridad **sin** el hash del propio ZIP:
    recomputarlo sobre el contenido extraido debe dar el mismo valor.
    """
    partes = [f"{ruta}|{hashes[ruta]}" for ruta in sorted(hashes)]
    return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()
