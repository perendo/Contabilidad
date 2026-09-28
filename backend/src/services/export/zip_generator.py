"""Generador determinista del ZIP de exportacion (SPEC-029 T020, research D5/D6).

Determinismo (test T013): dos generaciones sobre el mismo estado producen el
**mismo binario byte a byte**. Se logra con

- `ZipInfo` de fecha fija (`FECHA_ZIP`) en vez de la hora del sistema, y
  `external_attr` fijo, para que la cabecera de cada entrada sea estable;
- escritura de las rutas en orden alfabetico (`sorted`), que con los prefijos
  `001_`..`017_` coincide con el orden del catalogo;
- JSON sin `sort_keys` pero con orden de construccion estable.

La huella del binario completo (`sha256`) se calcula sobre los bytes finales;
la huella del contenido (`sha256_contenido`) va dentro del `manifest.json`
(`services.export.manifiesto.contenido_digest`).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from models.export.exportacion import LIMITE_BYTES
from services.export.bloques import Bloque
from services.export.errores import error
from services.export.manifiesto import contenido_digest, generar_manifiesto
from services.export.recopilar import BloqueRecopilado, bytes_bloque
from services.export.serializacion import volcar_json

__all__ = [
    "FECHA_ZIP",
    "MANIFIESTO",
    "ZipExportacion",
    "escribir_zip",
    "leer_manifiesto",
    "rutas_zip",
]

#: 1980-01-01 es el minimo del formato ZIP: cualquier valor fijo da igual, pero
#: ese evita que la cabecera contenga la hora real de la ejecucion.
FECHA_ZIP: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)
PERMISOS: int = 0o644 << 16
#: Nombre del inventario en la raiz del ZIP (`export-layout.md` 2).
MANIFIESTO = "manifest.json"


@dataclass
class ZipExportacion:
    """Resultado de `escribir_zip`: el binario y sus huellas."""

    contenido: bytes
    sha256: str
    sha256_contenido: str
    manifiesto: dict[str, Any]
    tamano_bytes: int
    hashes_bloques: dict[str, str] = field(default_factory=dict)
    #: Inventario completo (17 obligatorios + ficheros inyectados como el SII),
    #: que es lo que `persistir` graba en `ManifiestoBloque`.
    inventario: list[BloqueRecopilado] = field(default_factory=list)

    @property
    def n_bloques(self) -> int:
        """Numero de ficheros de bloque dentro del ZIP."""
        return len(self.hashes_bloques)


def _zipinfo(ruta: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=ruta, date_time=FECHA_ZIP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = PERMISOS
    info.create_system = 3
    return info


def _bloque_extra(ruta: str, datos: bytes, huella: str) -> BloqueRecopilado:
    """Linea de inventario para un fichero JSON inyectado (`entradas_extra`).

    `bloques/datos_sii/facturas_emitidas.json` se registra con el nombre
    `datos_sii.facturas_emitidas` y el `fichero` relativo, de forma que la
    verificacion de US2 lo encuentre por la misma ruta que los demas bloques.
    """
    relativo = ruta.removeprefix("bloques/")
    nombre = relativo[: -len(".json")].replace("/", ".")
    conteo = 0
    try:
        conteo = int(json.loads(datos.decode("utf-8")).get("conteo_registros", 0))
    except (ValueError, UnicodeDecodeError):
        conteo = 0
    return BloqueRecopilado(
        bloque=Bloque(
            nombre=nombre,
            fichero=relativo,
            descripcion="Fichero adicional del bloque SII",
            tablas=(),
        ),
        conteo_registros=conteo,
        sha256=huella,
    )


def escribir_zip(
    empresa_id: int,
    bloques: list[BloqueRecopilado],
    *,
    ejercicio_desde: int | None = None,
    ejercicio_hasta: int | None = None,
    fecha_generacion: datetime,
    tipo: str = "INTEGRAL",
    numero_exportacion: int | None = None,
    entradas_extra: dict[str, bytes] | None = None,
) -> ZipExportacion:
    """Construye el ZIP completo y calcula sus huellas.

    `entradas_extra` permite inyectar ficheros ya serializados (el bloque SII de
    US3) sin romper el orden determinista: se mezclan con el resto y todas se
    ordenan alfabeticamente antes de escribirse.
    """
    payloads: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for recopilado in bloques:
        ruta = recopilado.bloque.ruta
        if not ruta:
            continue
        datos = bytes_bloque(recopilado)
        huella = hashlib.sha256(datos).hexdigest()
        recopilado.sha256 = huella
        payloads[ruta] = datos
        hashes[ruta] = huella
    # Los ficheros inyectados (bloque SII de US3) tambien entran en el manifiesto,
    # con su conteo leido del propio JSON, para que `n_bloques` y la lista
    # `bloques` sean consistentes y verificables.
    inventario: list[BloqueRecopilado] = list(bloques)
    for ruta, datos in sorted((entradas_extra or {}).items()):
        huella = hashlib.sha256(datos).hexdigest()
        payloads[ruta] = datos
        hashes[ruta] = huella
        inventario.append(_bloque_extra(ruta, datos, huella))

    manifiesto = generar_manifiesto(
        empresa_id,
        inventario,
        ejercicio_desde=ejercicio_desde,
        ejercicio_hasta=ejercicio_hasta,
        fecha_generacion=fecha_generacion,
        sha256_contenido=contenido_digest(hashes),
        numero_exportacion=numero_exportacion,
        tipo=tipo,
    )
    manifiesto["n_bloques"] = len(hashes)
    payloads[MANIFIESTO] = volcar_json(manifiesto)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archivo:
        for ruta in sorted(payloads):
            archivo.writestr(_zipinfo(ruta), payloads[ruta])
    contenido = buffer.getvalue()
    if len(contenido) > LIMITE_BYTES:
        raise error(
            "exportacion_demasiado_grande",
            (
                f"La exportacion ocupa {len(contenido)} bytes y supera el limite de "
                f"{LIMITE_BYTES}; filtra por rango de ejercicios"
            ),
            422,
        )
    return ZipExportacion(
        contenido=contenido,
        sha256=hashlib.sha256(contenido).hexdigest(),
        sha256_contenido=manifiesto["sha256_contenido"],
        manifiesto=manifiesto,
        tamano_bytes=len(contenido),
        hashes_bloques=hashes,
        inventario=inventario,
    )


def rutas_zip(contenido: bytes) -> list[str]:
    """Rutas del ZIP en orden alfabetico, como quedaron escritas."""
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        return sorted(archivo.namelist())


def leer_manifiesto(contenido: bytes) -> dict[str, Any]:
    """Lee y parsea el `manifest.json` de la raiz del ZIP."""
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        crudo = archivo.read(MANIFIESTO)
    return json.loads(crudo.decode("utf-8"))
