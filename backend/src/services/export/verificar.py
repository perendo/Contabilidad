"""Verificacion de integridad de una exportacion (SPEC-029 T033, US2).

`verificar_exportacion` relee el blob **inmutable** de la empresa activa y
comprueba tres cosas (research D6, `export-layout.md` 5):

1. el SHA-256 del binario completo coincide con `ManifiestoExportacion.sha256_fichero`;
2. el `tenant_id` del `manifest.json` interior es el `empresa_id` de la sesion
   (constitution III: una exportacion jamas puede contener otro tenant);
3. el conteo de registros de cada bloque del manifiesto coincide con el
   `conteo_registros` y con el numero real de registros del JSON del ZIP.

Ademas recalcula `sha256_contenido` sobre los ficheros de bloque extraidos, de
modo que una alteracion de un solo bloque se detecta aunque el manifiesto de la
base de datos se hubiera tocado. El resultado es `{integro, ...}`: nunca lanza
porque el ZIP este manipulado, solo si la exportacion no existe, no esta
`lista` o no tiene blob.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
import zlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.export.blob_exportacion import BlobExportacion
from models.export.exportacion import Exportacion
from services.audit import registrar_auditoria
from services.export.errores import error
from services.export.manifiesto import contenido_digest
from services.export.persistir import (
    obtener_blob,
    obtener_exportacion,
    obtener_manifiesto,
)

__all__ = ["auditar", "verificar_contenido", "verificar_exportacion"]

AUDITAR = "VERIFICAR_EXPORTACION"

def _leer_json(archivo: zipfile.ZipFile, ruta: str) -> dict[str, Any] | None:
    try:
        crudo = archivo.read(ruta)
    except KeyError:
        return None
    return json.loads(crudo.decode("utf-8"))


def _ruta_bloque(linea: dict[str, Any]) -> str:
    """Ruta dentro del ZIP de una linea del manifiesto.

    Las lineas de bloque llevan su `fichero`; si no lo traen, se deduce del
    nombre del bloque (`bloques/<bloque>.json`).
    """
    fichero = linea.get("fichero")
    if isinstance(fichero, str) and fichero.endswith(".json"):
        return f"bloques/{fichero}"
    return f"bloques/{linea['bloque']}.json"


def verificar_contenido(
    contenido: bytes, empresa_id: int, esperado_fichero: str | None
) -> dict[str, Any]:
    """Compara el ZIP con su manifiesto y con la empresa activa.

    Devuelve el contrato de US2: `integro`, las dos huellas, el detalle por
    bloque y la lista de `diferencias` (vacia si todo cuadra).
    """
    calculado = hashlib.sha256(contenido).hexdigest()
    bloques: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
            veredicto = _verificar_zip(
                archivo, empresa_id, calculado, esperado_fichero, bloques
            )
    except (zipfile.BadZipFile, zlib.error, OSError):
        # Un byte alterado puede romper el stream deflate: se detecta como
        # corrupcion sin llegar a leer ningun bloque (FR-002).
        return {
            "integro": False,
            "sha256_calculado": calculado,
            "sha256_manifiesto": esperado_fichero,
            "bloques": [],
            "diferencias": [
                {
                    "tipo": "zip_corrupto",
                    "esperado": "archivo ZIP legible",
                    "encontrado": None,
                    "detalle": "El binario no se puede descomprimir: esta alterado",
                }
            ],
        }
    return veredicto


def _verificar_zip(
    archivo: zipfile.ZipFile,
    empresa_id: int,
    calculado: str,
    esperado_fichero: str | None,
    bloques: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compara el ZIP abierto con su manifiesto y con la empresa activa."""
    diferencias: list[dict[str, Any]] = []
    if esperado_fichero is not None and calculado != esperado_fichero:
        diferencias.append(
            {
                "tipo": "huella_fichero",
                "esperado": esperado_fichero,
                "encontrado": calculado,
                "detalle": "El SHA-256 del ZIP no coincide con el manifiesto",
            }
        )
    manifiesto = _leer_json(archivo, "manifest.json")
    if manifiesto is None:
        return {
            "integro": False,
            "sha256_calculado": calculado,
            "sha256_manifiesto": esperado_fichero,
            "bloques": [],
            "diferencias": [
                {
                    "tipo": "manifiesto_ausente",
                    "esperado": "manifest.json",
                    "encontrado": None,
                    "detalle": "El ZIP no contiene manifest.json en la raiz",
                }
            ],
        }
    tenant = manifiesto.get("tenant_id")
    if tenant != empresa_id:
        diferencias.append(
            {
                "tipo": "tenant",
                "esperado": empresa_id,
                "encontrado": tenant,
                "detalle": "El tenant_id del manifiesto no es la empresa activa",
            }
        )
    hashes: dict[str, str] = {}
    for linea in manifiesto.get("bloques", []):
        ruta = _ruta_bloque(linea)
        payload = _leer_json(archivo, ruta)
        if payload is None:
            diferencias.append(
                {
                    "tipo": "bloque_ausente",
                    "bloque": linea["bloque"],
                    "esperado": linea["conteo_registros"],
                    "encontrado": 0,
                    "detalle": f"El ZIP no contiene {ruta}",
                }
            )
            bloques.append(
                {
                    "bloque": linea["bloque"],
                    "esperados": int(linea["conteo_registros"]),
                    "encontrados": 0,
                    "coincide": False,
                }
            )
            continue
        encontrados = int(payload.get("conteo_registros", -1))
        reales = len(payload.get("registros", []))
        huella = hashlib.sha256(archivo.read(ruta)).hexdigest()
        hashes[ruta] = huella
        esperado_bloque = linea.get("sha256")
        coincide = (
            encontrados
            == reales
            == int(linea["conteo_registros"])
            and (esperado_bloque is None or esperado_bloque == huella)
        )
        bloques.append(
            {
                "bloque": linea["bloque"],
                "esperados": int(linea["conteo_registros"]),
                "encontrados": encontrados,
                "coincide": coincide,
            }
        )
        if not coincide:
            diferencias.append(
                {
                    "tipo": "conteo_bloque",
                    "bloque": linea["bloque"],
                    "esperado": int(linea["conteo_registros"]),
                    "encontrado": encontrados,
                    "detalle": (
                        f"El manifiesto declara {linea['conteo_registros']}, el JSON "
                        f"declara {encontrados} y contiene {reales} registros"
                    ),
                }
            )
    recomputado = contenido_digest(hashes)
    esperado_contenido = manifiesto.get("sha256_contenido")
    if esperado_contenido != recomputado:
        diferencias.append(
            {
                "tipo": "huella_contenido",
                "esperado": esperado_contenido,
                "encontrado": recomputado,
                "detalle": "El contenido del ZIP no corresponde a su manifiesto",
            }
        )
    return {
        "integro": not diferencias,
        "sha256_calculado": calculado,
        "sha256_manifiesto": esperado_fichero,
        "sha256_contenido": recomputado,
        "sha256_contenido_manifiesto": esperado_contenido,
        "bloques": bloques,
        "diferencias": diferencias,
    }


async def auditar(
    db: AsyncSession,
    empresa_id: int,
    fila: Exportacion,
    veredicto: dict[str, Any],
    actor: str | None,
    ip: str | None,
) -> None:
    """Registro inmutable `VERIFICAR_EXPORTACION` en la misma transaccion."""
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion=AUDITAR,
        entidad="Exportacion",
        entidad_id=fila.id,
        payload={
            "integro": veredicto["integro"],
            "sha256_calculado": veredicto["sha256_calculado"],
            "sha256_manifiesto": veredicto["sha256_manifiesto"],
            "n_diferencias": len(veredicto["diferencias"]),
        },
        usuario=actor,
        ip=ip,
    )


async def verificar_exportacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    exportacion_id,
    actor: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    """Verifica la integridad de la exportacion de la empresa activa (US2)."""
    fila: Exportacion = await obtener_exportacion(db, empresa_id, exportacion_id)
    if fila.estado.value != "lista":
        raise error(
            "exportacion_no_lista",
            f"Solo se puede verificar una exportacion en estado 'lista' (actual: {fila.estado.value})",
            409,
        )
    manifiesto = await obtener_manifiesto(db, empresa_id, fila.id)
    cabecera = manifiesto[0] if manifiesto else None
    blob: BlobExportacion = await obtener_blob(db, empresa_id, fila.id)
    veredicto = verificar_contenido(
        bytes(blob.contenido), empresa_id, cabecera.sha256_fichero if cabecera else fila.sha256
    )
    veredicto["exportacion_id"] = str(fila.id)
    veredicto["numero_exportacion"] = fila.numero_exportacion
    veredicto["verificada_at"] = cabecera.fecha_generacion.isoformat() if cabecera else None
    await auditar(db, empresa_id, fila, veredicto, actor, ip)
    return veredicto
