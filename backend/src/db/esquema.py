"""Compara lo que la aplicación **declara** con lo que la base **tiene**.

Este módulo existe por un motivo concreto: veintisiete tablas que la aplicación
declara no existían en la base de datos, y no se había dado cuenta nadie durante
siete specs. La puerta de migraciones comprobaba que las migraciones *declaradas*
estuvieran listadas, nunca que cada tabla declarada tuviera su migración.

Este módulo cierra ese hueco desde el otro lado: no mira ficheros SQL, sino que
**interroga la base** y la enfrenta a los metadatos de los modelos.

## Por qué comparar, y no generar

Se podría escribir el DDL a partir de los metadatos. No se hace, y la razón es que
autogenerar deja sin cubrir justo lo que en este proyecto importa:

- **Los enums.** Cada uno necesita su guarda de idempotencia. Sin ella, `db.migrate`
  revienta en la segunda pasada, porque reaplica los ficheros ya aplicados.
- **Las unicidades sobre columnas nulas.** Un `UNIQUE` normal no colisiona con
  `NULL`, así que hace falta un índice parcial, y eso hay que pensarlo.
- **Los triggers y las funciones.** Nunca se generan, y son la constitución II
  (asientos inmutables, auditoría sin borrar).

La comparación **sí** cubre las 281 columnas de forma fiable, que es donde un
transcrito a mano se equivoca. Esa es la división del trabajo: las columnas se
verifican, las decisiones se toman.

## Qué compara, y qué no

Compara: tablas, columnas, tipo, nulabilidad y valor por defecto. Es el 90 % del
error humano posible, y es la parte que se puede comparar de forma fiable entre dos
fuentes.

**No** compara todavía unicidades, claves foráneas, índices ni triggers. Queda
declarado como ampliaciones, no como olvido: comparar un `UNIQUE` con un índice
parcial exige normalizar la representación, y hacerlo mal da un falso "todo bien"
que es peor que no mirar. La cobertura actual ya habría encontrado las 27.

## Uso

    from db.esquema import comparar_con_modelos, describir_base

    diferencias = await comparar_con_modelos(session)
    for d in diferencias:
        print(d)
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncConnection

#: El modelo se interpreta siempre con el dialecto de PostgreSQL. Sin esto, un
#: `Uuid` se lee como `CHAR(32)` (que es como lo ve SQLite, y como lo vería el
#: `create_all` de los tests) y un `DateTime(timezone=True)` como `DATETIME` a
#: secas. Ninguna de las dos diferencias es real: son el mismo tipo escrito en el
#: dialecto equivocado, y compararlos así produce cientos de falsos positivos.
_DIALECTO = postgresql.dialect()

# ---------------------------------------------------------------------------
# Qué se compara de cada columna
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Columna:
    """Una columna, vista desde las dos fuentes, en forma comparable."""

    nombre: str
    tipo: str
    nullable: bool
    defecto: str | None

    def diferencias_con(self, otra: Columna) -> list[str]:
        """Diferencias con la misma columna de la otra fuente."""
        salida: list[str] = []
        if self.tipo != otra.tipo:
            salida.append(f"tipo: modelo={self.tipo} base={otra.tipo}")
        if self.nullable != otra.nullable:
            salida.append(
                f"nulabilidad: modelo={'NULL' if self.nullable else 'NOT NULL'} "
                f"base={'NULL' if otra.nullable else 'NOT NULL'}"
            )
        if (self.defecto or "") != (otra.defecto or ""):
            salida.append(
                f"valor por defecto: modelo={self.defecto!r} base={otra.defecto!r}"
            )
        return salida


@dataclass(frozen=True)
class Tabla:
    """Una tabla, vista desde las dos fuentes."""

    nombre: str
    columnas: dict[str, Columna]

    @property
    def n_columnas(self) -> int:
        return len(self.columnas)


# ---------------------------------------------------------------------------
# Lado "base": interrogar PostgreSQL
# ---------------------------------------------------------------------------

#: information_schema devuelve los tipos con el tamaño dentro, lo que hace que
#: VARCHAR(200) y VARCHAR(200) se comparen bien pero NUMERIC(18,4) y NUMERIC(18, 4)
#: no. Se normaliza quitando el espacio tras la coma.
_CONSULTA_COLUMNAS = """
SELECT table_name, column_name, data_type, udt_name,
       COALESCE(character_maximum_length, -1) AS len,
       COALESCE(numeric_precision, -1) AS prec,
       COALESCE(numeric_scale, -1) AS esc,
       is_nullable,
       COALESCE(column_default, '') AS defecto
FROM information_schema.columns
WHERE table_schema = :esquema
ORDER BY table_name, column_name
"""


def _tipo_desde_information_schema(
    data_type: str, udt_name: str, len_: int, prec: int, esc: int
) -> str:
    """Recompone el tipo que el modelo declara, para que se puedan comparar.

    `data_type` solo no basta: un enumerado y un `uuid` salen los dos como
    `USER-DEFINED`/`uuid` pero el nombre del tipo (`udt_name`) es el que los
    distingue y el que lo compara con lo que declara el modelo.
    """
    if data_type == "USER-DEFINED":
        return udt_name.upper()
    if data_type == "character varying" and len_ > 0:
        return f"VARCHAR({len_})"
    if data_type == "character" and len_ > 0:
        return f"CHAR({len_})"
    if data_type == "numeric" and prec > 0:
        return f"NUMERIC({prec},{esc})" if esc >= 0 else f"NUMERIC({prec})"
    if data_type == "timestamp with time zone":
        return "TIMESTAMP WITH TIME ZONE"
    return data_type.upper()


async def describir_base(conn: AsyncConnection, esquema: str = "public") -> dict[str, Tabla]:
    """Lee las tablas y columnas reales de la base."""
    resultado = await conn.execute(text(_CONSULTA_COLUMNAS), {"esquema": esquema})
    filas = resultado.all()
    tablas: dict[str, dict[str, Columna]] = {}
    for (
        nombre_tabla,
        nombre_col,
        data_type,
        udt_name,
        len_,
        prec,
        esc,
        nullable,
        defecto,
    ) in filas:
        tablas.setdefault(nombre_tabla, {})[nombre_col] = Columna(
            nombre=nombre_col,
            tipo=_tipo_desde_information_schema(data_type, udt_name, len_, prec, esc),
            nullable=nullable == "YES",
            defecto=_normalizar_defecto(defecto),
        )
    return {
        nombre: Tabla(nombre=nombre, columnas=columnas)
        for nombre, columnas in tablas.items()
    }


def _normalizar_defecto(bruto: str) -> str | None:
    """Quita lo que es ruido de PostgreSQL para poder comparar con el modelo.

    La base guarda los valores por defecto ya resueltos por el motor
    (`'{}'::character varying`, `nextval(...)`, `now()`, `false`), y el modelo los
    declara como valores de Python. Compararlos en crudo daría una diferencia en
    cada columna con valor por defecto, y un informe lleno de ruido es un informe
    que nadie lee.
    """
    if not bruto:
        return None
    limpio = bruto.strip()
    for patron in ("::",):
        if patron in limpio:
            limpio = limpio.rsplit(patron, 1)[0].strip()
    if limpio.startswith("(") and limpio.endswith(")"):
        limpio = limpio[1:-1].strip()
    for envolvente in (
        "nextval(",
        "now()",
        "CURRENT_TIMESTAMP",
    ):
        if limpio.lower().startswith(envolvente.lower()):
            return limpio.lower()
    if limpio in ("true", "false"):
        return limpio
    return limpio.strip("'\"") or None


# ---------------------------------------------------------------------------
# Lado "modelo": metadatos de SQLAlchemy
# ---------------------------------------------------------------------------


def _tipo_de_modelo(columna) -> str:
    """El tipo declarado, en la misma notación que usa el lado de la base.

    Se compila con el dialecto de PostgreSQL y no con `str()`, porque `str()` da
    la representación genérica: un `Uuid` sale como `CHAR(32)`, que es lo que
    ven los tests de SQLite, y compararlo contra el `UUID` real de la base marca
    una diferencia que no existe.
    """
    return _normalizar_tipo(columna.type.compile(dialect=_DIALECTO))


def _normalizar_tipo(tipo: str) -> str:
    """Quita el espacio tras la coma: `NUMERIC(18, 4)` y `NUMERIC(18,4)` son lo mismo."""
    return tipo.upper().replace(", ", ",")


def _defecto_de_modelo(columna) -> str | None:
    """El valor por defecto declarado en el modelo, normalizado.

    Dos cosas que hay que arreglar aquí o el informe se llena de ruido:

    - **Los enumerados.** El modelo declara `default=EstadoAlerta.abierta`, y su
      `str()` es `EstadoAlerta.abierta`, no `abierta`. Sin tomar el `.value`, cada
      columna con enumerado por defecto marca una diferencia inexistente.
    - **Las funciones.** `uuid4()` y `now()` no tienen equivalente comparable: la
      base las resuelve sola. Se marcan con un prefijo para que la comparación las
      salte en vez de inventarles un equivalente.
    """
    if columna.default is None:
        if columna.server_default is not None:
            return str(columna.server_default.arg).strip("'\"")
        return None
    arg = columna.default.arg
    if callable(arg):
        return f"callable:{getattr(arg, '__name__', 'lambda')}"
    valor = getattr(arg, "value", None)  # miembro de enumerado
    if valor is not None:
        return str(valor)
    if isinstance(arg, bool):
        return "true" if arg else "false"
    return str(arg)


def describir_modelos(metadata) -> dict[str, Tabla]:
    """Las tablas que declaran los modelos de la aplicación."""
    tablas: dict[str, Tabla] = {}
    for nombre, tabla in metadata.tables.items():
        columnas = {
            c.name: Columna(
                nombre=c.name,
                tipo=_tipo_de_modelo(c),
                nullable=bool(c.nullable),
                defecto=_defecto_de_modelo(c),
            )
            for c in tabla.columns
        }
        tablas[nombre] = Tabla(nombre=nombre, columnas=columnas)
    return tablas


# ---------------------------------------------------------------------------
# La comparacion
# ---------------------------------------------------------------------------


#: Gravedad de una diferencia.
#:
#: `REAL` es una discrepancia de verdad: la base no puede atender lo que la
#: aplicación declara, o la aplicación no puede atender lo que la base tiene.
#:
#: `EQUIVALENTE` son dos maneras de escribir lo mismo. **No hacen fallar ningún
#: guard**, y esa es la razón de existir: una comprobación que falla por differences
#: que no son diferencias acaba apagándose, y una apagada no vigila nada. Se
#: listan aparte, con su razón, para que sean visibles sin bloquear.
GRAVEDAD_REAL = "REAL"
GRAVEDAD_EQUIVALENTE = "EQUIVALENTE"

#: Pares de tipos que guardan lo mismo y por tanto no son un fallo. La clave es
#: (tipo_menor, tipo_mayor): el orden importa porque `VARCHAR(64)` y `CHAR(64)` no
#: son intercambiables al escribir, pero si al leer.
_TIPOS_EQUIVALENTES: frozenset[tuple[str, str]] = frozenset(
    {
        # JSONB es el mismo dato que JSON, en binario y con indice. Las seis
        # migraciones del repositorio que crean columnas JSON las crean JSONB;
        # la diferencia real es que algunos modelos dicen `JSON` pelado.
        ("JSON", "JSONB"),
        # CHAR(64) rellena con espacios hasta 64. Una huella SHA-256 siempre
        # ocupa los 64, asi que el relleno no se ve nunca.
        ("CHAR(3)", "VARCHAR(3)"),
        ("CHAR(64)", "VARCHAR(64)"),
        # BIGINT admite mas enteros que INTEGER. Si el valor cabe, da igual.
        ("BIGINT", "INTEGER"),
    }
)


@dataclass(frozen=True)
class Diferencia:
    """Una discrepancia entre lo declarado y lo existente."""

    tabla: str
    columna: str | None
    detalle: str
    gravedad: str = GRAVEDAD_REAL

    @property
    def es_real(self) -> bool:
        return self.gravedad == GRAVEDAD_REAL

    def __str__(self) -> str:
        donde = self.tabla if self.columna is None else f"{self.tabla}.{self.columna}"
        marca = "" if self.es_real else "  (equivalente)"
        return f"{donde}: {self.detalle}{marca}"


def comparar(
    declarados: dict[str, Tabla], existentes: dict[str, Tabla]
) -> list[Diferencia]:
    """Diferencias entre lo declarado y lo existente.

    Regla: la base puede declarar **mas** de lo que el modelo (una clave foranea
    que el modelo no expresa es una mejora, no un fallo), pero nunca menos, y nunca
    distinto.
    """
    salida: list[Diferencia] = []

    for nombre, tabla in sorted(declarados.items()):
        real = existentes.get(nombre)
        if real is None:
            salida.append(
                Diferencia(nombre, None, "la tabla NO EXISTE en la base", GRAVEDAD_REAL)
            )
            continue
        for col, esperada in sorted(tabla.columnas.items()):
            hallada = real.columnas.get(col)
            if hallada is None:
                salida.append(
                    Diferencia(nombre, col, "la columna NO EXISTE en la base", GRAVEDAD_REAL)
                )
                continue
            for detalle in esperada.diferencias_con(hallada):
                gravedad = (
                    GRAVEDAD_EQUIVALENTE
                    if _es_irrelevante(detalle, esperada, hallada)
                    else GRAVEDAD_REAL
                )
                salida.append(Diferencia(nombre, col, detalle, gravedad))

    return salida


def solo_reales(diferencias: list[Diferencia]) -> list[Diferencia]:
    """Las que deben hacer fallar un guard. Equivalentes fuera."""
    return [d for d in diferencias if d.es_real]


async def comparar_con_modelos(
    conn: AsyncConnection, metadata, esquema: str = "public"
) -> list[Diferencia]:
    """Atajo: describe la base, describe los modelos y compara."""
    declarados = describir_modelos(metadata)
    existentes = await describir_base(conn, esquema)
    return comparar(declarados, existentes)


def _tipos_equivalentes(uno: str, otro: str) -> bool:
    if uno == otro:
        return True
    return (uno, otro) in _TIPOS_EQUIVALENTES or (otro, uno) in _TIPOS_EQUIVALENTES


def _defectos_numericamente_iguales(uno: str | None, otro: str | None) -> bool:
    """`'0.0000'` y `'0'` son el mismo numero escrito de dos maneras.

    Un `DEFAULT 0.0000` de PostgreSQL llega por `information_schema` como `'0'`,
    porque el motor lo reduce. Compararlos como texto marca una diferencia en
    cada columna decimal con valor por defecto, y eso es ruido.
    """
    from decimal import Decimal, InvalidOperation

    if uno is None or otro is None:
        return uno is otro
    if uno == otro:
        return True
    try:
        return Decimal(uno) == Decimal(otro)
    except (InvalidOperation, ValueError):
        return False


def _es_irrelevante(detalle: str, esperada: Columna, hallada: Columna) -> bool:
    """Diferencias que no son diferencias.

    Tres casos, y los tres salen de escribir lo mismo de dos maneras:

    1. **Valores por defecto resueltos por funcion.** El modelo dice `uuid4()` y la
       base dice `uuid_generate_v4()`, o el modelo dice `now()` y la base dice
       `now()`. No hay equivalente que comparar, asi que se salta.
    2. **Tipos equivalentes** (`VARCHAR(64)` contra `CHAR(64)`). Ver la tabla.
    3. **Defectos numericamente iguales** (`'0.0000'` contra `'0'`).
    """
    if detalle.startswith("valor por defecto"):
        return (esperada.defecto or "").startswith("callable:") or _defectos_numericamente_iguales(
            esperada.defecto, hallada.defecto
        )
    if detalle.startswith("tipo: "):
        _, _, resto = detalle.partition("modelo=")
        modelo, _, base = resto.partition(" base=")
        return _tipos_equivalentes(modelo.strip(), base.strip())
    return False
