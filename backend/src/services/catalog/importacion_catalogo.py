"""Importacion de actualizaciones normativas del catalogo (SPEC-025 US2).

Parser CSV/JSON con validacion Pydantic v2 (errores por fila), servicio
``importar_catalogo`` (version borrador ``es_migracion=true`` con proyeccion,
operaciones y mapeos en una sola transaccion ACID) y el validador
``validar_mapeo_completo`` (FR-004) que bloquea la activacion cuando una
cuenta suprimida con saldo distinto de cero se queda sin destino.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.writer import audit_escribir
from services.catalog import _comun
from services.catalog.errores import CatalogoError

__all__ = [
    "ImportacionCatalogo",
    "MapeoImport",
    "OperacionImport",
    "decodificar",
    "importar_catalogo",
    "parsear_csv",
    "parsear_json",
    "validar_mapeo_completo",
]

_CODIGO = r"^\d{1,8}$"


class OperacionImport(BaseModel):
    operacion: Literal["alta", "renombrado", "baja"]
    codigo: str = Field(pattern=_CODIGO)
    nombre: str | None = None
    padre_codigo: str | None = Field(None, pattern=_CODIGO)
    destino_codigo: str | None = Field(None, pattern=_CODIGO)

    @field_validator("nombre", "padre_codigo", "destino_codigo", mode="before")
    @classmethod
    def _vacio_a_none(cls, valor: Any) -> Any:
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor


class MapeoImport(BaseModel):
    origen_codigo: str = Field(pattern=_CODIGO)
    destino_codigo: str = Field(pattern=_CODIGO)


class ImportacionCatalogo(BaseModel):
    codigo_version: str = Field(min_length=1, max_length=20)
    fecha_inicio: date
    fecha_fin: date | None = None
    operaciones: list[OperacionImport] = Field(default_factory=list)
    mapeo: list[MapeoImport] = Field(default_factory=list)


def decodificar(contenido: bytes) -> str:
    """UTF-8 con BOM si es posible; fallback ISO-8859-15 (CSV español)."""
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("iso-8859-15")


def _errores_pydantic(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "campo": ".".join(str(p) for p in err["loc"]),
            "motivo": err["msg"],
        }
        for err in exc.errors()
    ]


def parsear_json(contenido: str) -> ImportacionCatalogo:
    """Parsea el body/fichero JSON; cualquier error -> 422 con motivos."""
    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise CatalogoError(
            "fichero_invalido", f"JSON invalido: {exc.msg} (linea {exc.lineno})", 422
        ) from exc
    if not isinstance(datos, dict):
        raise CatalogoError(
            "fichero_invalido", "Se esperaba un objeto JSON con la importacion", 422
        )
    try:
        return ImportacionCatalogo.model_validate(datos)
    except ValidationError as exc:
        raise CatalogoError(
            "fichero_invalido",
            "La importacion no supera la validacion",
            422,
            extra={"errores": _errores_pydantic(exc)},
        ) from exc


def parsear_csv(contenido: str) -> list[dict[str, Any]]:
    """Parsea el CSV de operaciones (cabecera operacion,codigo,...).

    Una sola fila mal formada rechaza la importacion completa con el listado
    ``errores=[{fila, motivo}]`` (T026).
    """
    lineas = [linea for linea in contenido.splitlines() if linea.strip()]
    if not lineas:
        raise CatalogoError("fichero_invalido", "El fichero CSV esta vacio", 422)
    delimitador = ";" if ";" in lineas[0] else ","
    lector = csv.DictReader(io.StringIO(contenido), delimiter=delimitador)
    campos = [(nombre or "").strip().lower() for nombre in (lector.fieldnames or [])]
    if "operacion" not in campos or "codigo" not in campos:
        raise CatalogoError(
            "fichero_invalido",
            "La cabecera CSV debe incluir las columnas operacion y codigo",
            422,
        )
    operaciones: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = []
    for indice, fila in enumerate(lector, start=2):
        limpia = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in fila.items()
            if k is not None
        }
        if not any(limpia.values()):
            continue
        try:
            operacion = OperacionImport.model_validate(limpia)
        except ValidationError as exc:
            errores.append(
                {"fila": indice, "motivo": _errores_pydantic(exc)[0]["motivo"]}
            )
            continue
        operaciones.append(operacion.model_dump())
    if errores:
        raise CatalogoError(
            "fila_invalida",
            f"{len(errores)} fila(s) del CSV no son validas",
            422,
            extra={"errores": errores},
        )
    if not operaciones:
        raise CatalogoError(
            "fichero_invalido", "El CSV no contiene operaciones", 422
        )
    return operaciones


async def importar_catalogo(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo_version: str,
    fecha_inicio: date,
    fecha_fin: date | None,
    operaciones: list[dict[str, Any]],
    mapeo: list[dict[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """Crea la version ``borrador`` de la normativa y sus mapeos (FR-002)."""
    version = await _comun.crear_version_completa(
        db,
        empresa_id=empresa_id,
        codigo=codigo_version,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        operaciones=operaciones,
        mapeo_explicito=mapeo,
        actor=actor,
        es_migracion=True,
    )
    pendientes = await _comun.pendientes_mapeo(db, empresa_id, version.id)
    conteo = await _comun.contar_version(db, empresa_id, version.id)
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor,
        action="IMPORTAR_CATALOGO",
        entity="catalogo_version",
        entity_id=str(version.id),
        payload={
            "codigo": codigo_version,
            "numero_version": version.numero_version,
            "operaciones": len(operaciones),
            "entradas_mapeo": len(mapeo),
            **conteo,
            "pendientes": pendientes,
        },
    )
    return {
        "version_id": str(version.id),
        **conteo,
        "pendientes_mapeo": pendientes,
    }


async def validar_mapeo_completo(
    db: AsyncSession, empresa_id: int, version_id: Any
) -> list[dict[str, str]]:
    """FR-004/FR-006: suprimidas con saldo != 0 y sin destino (bloquean).

    Los mapeos sin destino de cuentas con saldo cero se listan como aviso en
    ``pendientes_mapeo`` pero no impiden la activacion.
    """
    items = await _comun.pendientes_mapeo(db, empresa_id, version_id)
    return [item for item in items if item["motivo"] == "saldo_no_cero"]
