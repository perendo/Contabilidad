"""Recopilacion paginada de un bloque de datos (SPEC-029 T018, research D3/D4).

`construir_consulta_bloque` compone, para cada tabla del bloque:

1. el filtro **obligatorio** `empresa_col == empresa_id`, donde `empresa_id`
   viene de la sesion autenticada (constitution III, research D4);
2. el filtro opcional de rango de ejercicios, resuelto desde la propia tabla
   (`ejercicio` entero, `fecha`, o rango `fecha_ini`/`fecha_fin`) o desde su
   tabla padre para las hijas sin fecha propia;
3. las columnas auxiliares `__ejercicio` y `__fecha` que alimentan
   `ejercicio_min/max` y `fecha_min/max` del manifiesto.

`recopilar_bloque` recorre las tablas del bloque con `stream()` en lotes de
`LOTE_REGISTROS` (10.000) para no volcar una tabla entera en RAM, serializa cada
fila con `serializacion.serializar` (importes como cadenas de 4 decimales) y
devuelve el payload del bloque junto con sus metadatos de inventario.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from base import Base
from services.export.bloques import (
    BLOQUES_OBLIGATORIOS,
    COL_EJERCICIO,
    COL_FECHA,
    Bloque,
    TablaBloque,
)
from services.export.errores import error
from services.export.serializacion import serializar, volcar_json

__all__ = [
    "LOTE_REGISTROS",
    "BloqueRecopilado",
    "construir_consulta_bloque",
    "recopilar_bloque",
    "recopilar_todos",
]

#: Research D5: lotes de 10.000 registros por tabla.
LOTE_REGISTROS: int = 10_000


@dataclass
class BloqueRecopilado:
    """Payload del bloque mas los metadatos que van al manifiesto."""

    bloque: Bloque
    registros: list[dict[str, Any]] = field(default_factory=list)
    conteo_registros: int = 0
    ejercicio_min: int | None = None
    ejercicio_max: int | None = None
    fecha_min: date | None = None
    fecha_max: date | None = None
    #: SHA-256 de los bytes del JSON del bloque; lo calcula `zip_generator`.
    sha256: str | None = None
    #: Conteo por entidad, util para el detalle del ZIP y los tests.
    conteo_por_entidad: dict[str, int] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        """Cabecera minima + registros, segun `contracts/export-layout.md` 1."""
        return {
            "bloque": self.bloque.nombre,
            "descripcion": self.bloque.descripcion,
            "entidades_exportadas": list(self.bloque.entidades),
            "conteo_registros": self.conteo_registros,
            "ejercicio_min": self.ejercicio_min,
            "ejercicio_max": self.ejercicio_max,
            "conteo_por_entidad": dict(self.conteo_por_entidad),
            "registros": self.registros,
        }

    def finalizar(self) -> BloqueRecopilado:
        """Congela el conteo al de los registros realmente serializados."""
        self.conteo_registros = len(self.registros)
        return self


def _tabla(nombre: str) -> Any:
    tabla = Base.metadata.tables.get(nombre)
    if tabla is None:
        raise error(
            "bloque_desconocido",
            f"La tabla '{nombre}' del catalogo de exportacion no esta registrada",
            500,
        )
    return tabla


def _filtro_rango_columnas(
    tabla: Any, ejercicio_col: str | None, fecha_col: str | None, rango: tuple[str, str] | None,
    desde: int, hasta: int,
) -> ColumnElement[bool] | None:
    """Filtro de rango sobre una tabla concreta, o `None` si no aplica."""
    ini = date(desde, 1, 1)
    fin = date(hasta, 12, 31)
    if rango is not None:
        # Semantica de solapamiento: una version vigente que cruza el rango
        # entra completa (p. ej. el PGC 2025 de SPEC-025).
        return and_(tabla.c[rango[0]] <= fin, tabla.c[rango[1]] >= ini)
    if ejercicio_col is not None:
        return tabla.c[ejercicio_col].between(desde, hasta)
    if fecha_col is not None:
        return and_(tabla.c[fecha_col] >= ini, tabla.c[fecha_col] <= fin)
    return None


def _columna_fecha(tabla: Any) -> str | None:
    """Columna de fecha de negocio de la tabla: la primera `fecha*`, o `created_at`.

    `created_at` es la ultima opcion porque sirve para fechar filas de snapshot
    (presupuestos, desviaciones), pero **no** se usa nunca como filtro: es una
    columna tecnica y filtrar por ella dejaria fuera el plan de cuentas.
    """
    for columna in tabla.columns:
        if columna.name.startswith("fecha"):
            return columna.name
    return "created_at" if "created_at" in tabla.c else None


def _columna_fecha_negocio(tabla: Any) -> str | None:
    """Columna `fecha*` de la tabla, o `None` si no tiene fecha de negocio."""
    for columna in tabla.columns:
        if columna.name.startswith("fecha"):
            return columna.name
    return None


def _expresion_rango(
    tabla: Any, ref: TablaBloque, desde: int, hasta: int
) -> ColumnElement[bool] | None:
    """Filtro de rango de ejercicios para una tabla, o `None` si no aplica.

    Orden de resolucion: rango declarado, columna `ejercicio`, `fecha_col`
    declarada, tabla padre y, en ultimo termino, la primera columna `fecha*` de
    la propia tabla. Se comparan **fechas**, no `EXTRACT(year ...)`, para que la
    misma consulta funcione en PostgreSQL y en el SQLite de los tests.
    """
    directo = _filtro_rango_columnas(
        tabla,
        "ejercicio" if "ejercicio" in tabla.c else None,
        ref.fecha_col,
        ref.rango,
        desde,
        hasta,
    )
    if directo is not None:
        return directo
    if ref.padre is not None:
        padre = _tabla(ref.padre.tabla)
        filtro_padre = _filtro_rango_columnas(
            padre,
            ref.padre.ejercicio_col,
            ref.padre.fecha_col,
            (ref.padre.fecha_ini_col, ref.padre.fecha_fin_col)
            if ref.padre.fecha_ini_col and ref.padre.fecha_fin_col
            else None,
            desde,
            hasta,
        )
        if filtro_padre is None:
            return None
        vinculo = and_(
            tabla.c[ref.padre.clave] == padre.c["id"],
            padre.c[ref.padre.empresa_col] == tabla.c[ref.empresa_col],
        )
        return select(literal(1)).where(vinculo).where(filtro_padre).exists()
    # Sin padre declarado: se usa la primera columna `fecha*` de negocio. `created_at`
    # no filtra (es tecnica): un maestro como `account_plan` se exporta integro.
    return _filtro_rango_columnas(
        tabla, None, _columna_fecha_negocio(tabla), None, desde, hasta
    )


def _columna_auxiliar(tabla: Any, ref: TablaBloque, campo: str) -> Any:
    """Columna auxiliar `__ejercicio` / `__fecha` para el calculo de min/max.

    `__ejercicio` solo se resuelve desde una columna entera `ejercicio` (propia
    o del padre); si la tabla solo tiene fecha, el ejercicio se deduce en Python
    del ano de `__fecha`, sin usar `EXTRACT` (no existe en SQLite).
    """
    padre: Any = _tabla(ref.padre.tabla) if ref.padre is not None else None
    vinculo: Any = None
    if padre is not None and ref.padre is not None:
        vinculo = padre.c["id"] == tabla.c[ref.padre.clave]
    origen: Any = None
    if campo == COL_EJERCICIO:
        if "ejercicio" in tabla.c:
            origen = tabla.c["ejercicio"]
        elif padre is not None and ref.padre is not None and ref.padre.ejercicio_col:
            origen = padre.c[ref.padre.ejercicio_col]
    else:
        nombre = ref.fecha_col or _columna_fecha(tabla)
        if nombre is not None and nombre in tabla.c:
            origen = tabla.c[nombre]
        elif padre is not None and ref.padre is not None and ref.padre.fecha_col:
            origen = padre.c[ref.padre.fecha_col]
    if origen is None:
        return None
    if padre is not None and vinculo is not None and origen.table is padre:
        return select(origen).where(vinculo).correlate(tabla).scalar_subquery().label(campo)
    return origen.label(campo)


def columnas_tabla(tabla: Any, ref: TablaBloque) -> list[Any]:
    """Columnas visibles de la tabla (todas menos las excluidas)."""
    return [c for c in tabla.columns if c.name not in ref.excluir]


def construir_consulta_bloque(
    bloque: Bloque, empresa_id: int, desde: int | None, hasta: int | None
) -> dict[str, Select[Any]]:
    """Consultas del bloque, una por tabla, con empresa y rango ya aplicados."""
    consultas: dict[str, Select[Any]] = {}
    for ref in bloque.tablas:
        tabla = _tabla(ref.tabla)
        if ref.empresa_col not in tabla.c:
            raise error(
                "bloque_invalido",
                f"'{ref.tabla}' no tiene columna de empresa '{ref.empresa_col}'",
                500,
            )
        seleccion: list[Any] = list(columnas_tabla(tabla, ref))
        filtros: list[ColumnElement[bool]] = [tabla.c[ref.empresa_col] == empresa_id]
        if desde is not None and hasta is not None and ref.filtra_rango:
            rango = _expresion_rango(tabla, ref, desde, hasta)
            if rango is not None:
                filtros.append(rango)
        for etiqueta in (COL_EJERCICIO, COL_FECHA):
            auxiliar = _columna_auxiliar(tabla, ref, etiqueta)
            if auxiliar is not None:
                seleccion.append(auxiliar)
        consulta = select(*seleccion).where(and_(*filtros))
        # Orden determinista por clave primaria: dos generaciones del mismo
        # estado producen el mismo JSON (test T013).
        orden = list(tabla.primary_key.columns)
        consultas[ref.tabla] = consulta.order_by(*orden) if orden else consulta
    return consultas


async def _iterar(
    db: AsyncSession, consulta: Select[Any]
) -> AsyncIterator[dict[str, Any]]:
    """Recorre las filas de la consulta en lotes de `LOTE_REGISTROS`."""
    resultado = await db.stream(consulta.execution_options(yield_per=LOTE_REGISTROS))
    async for fila in resultado:
        yield dict(fila._mapping)


def _anotar(destino: BloqueRecopilado, fila: dict[str, Any]) -> dict[str, Any]:
    """Extrae los auxiliares del registro y actualiza los min/max del bloque.

    Cuando la tabla no aporta columna `ejercicio`, el ejercicio se deduce del
    ano de la fecha (sin `EXTRACT`, que SQLite no soporta).
    """
    ejercicio = fila.pop(COL_EJERCICIO, None)
    fecha = fila.pop(COL_FECHA, None)
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    if isinstance(ejercicio, (date, datetime)):
        fecha = ejercicio.date() if isinstance(ejercicio, datetime) else ejercicio
        ejercicio = fecha.year
    if isinstance(ejercicio, str) and ejercicio.isdigit():
        ejercicio = int(ejercicio)
    if isinstance(ejercicio, (int, Decimal)) and not isinstance(ejercicio, bool):
        valor = int(ejercicio)
        destino.ejercicio_min = (
            valor if destino.ejercicio_min is None else min(destino.ejercicio_min, valor)
        )
        destino.ejercicio_max = (
            valor if destino.ejercicio_max is None else max(destino.ejercicio_max, valor)
        )
    if isinstance(fecha, date):
        destino.fecha_min = fecha if destino.fecha_min is None else min(destino.fecha_min, fecha)
        destino.fecha_max = fecha if destino.fecha_max is None else max(destino.fecha_max, fecha)
    return {clave: serializar(valor) for clave, valor in fila.items()}


async def recopilar_bloque(
    db: AsyncSession,
    bloque: Bloque,
    empresa_id: int,
    desde: int | None = None,
    hasta: int | None = None,
) -> BloqueRecopilado:
    """Recopila todas las tablas del bloque de la empresa activa.

    El `empresa_id` se aplica en cada consulta; el rango de ejercicios solo
    afecta a las tablas que declaran ejercicio o fecha (research D3), por lo que
    los bloques atemporales (plan de cuentas, terceros, configuracion) se
    exportan integros.
    """
    destino = BloqueRecopilado(bloque=bloque)
    consultas = construir_consulta_bloque(bloque, empresa_id, desde, hasta)
    refs = {ref.tabla: ref for ref in bloque.tablas}
    for nombre, consulta in consultas.items():
        ref = refs[nombre]
        total_tabla = 0
        async for fila in _iterar(db, consulta):
            destino.registros.append(_anotar(destino, fila))
            total_tabla += 1
        destino.conteo_por_entidad[ref.nombre_entidad] = (
            destino.conteo_por_entidad.get(ref.nombre_entidad, 0) + total_tabla
        )
    return destino.finalizar()


async def recopilar_todos(
    db: AsyncSession,
    empresa_id: int,
    desde: int | None = None,
    hasta: int | None = None,
    bloques: tuple[Bloque, ...] | None = None,
) -> list[BloqueRecopilado]:
    """Recopila los bloques indicados (por defecto, los 17 obligatorios)."""
    return [
        await recopilar_bloque(db, bloque, empresa_id, desde, hasta)
        for bloque in (bloques if bloques is not None else BLOQUES_OBLIGATORIOS)
    ]


def bytes_bloque(recopilado: BloqueRecopilado) -> bytes:
    """JSON determinista del bloque, listo para `ZipFile.writestr`."""
    return volcar_json(recopilado.payload())


def ahora_utc() -> datetime:
    """Instante actual en UTC, truncado al segundo."""
    return datetime.now(timezone.utc).replace(microsecond=0)
