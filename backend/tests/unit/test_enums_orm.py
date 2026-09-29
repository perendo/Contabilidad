"""Dos cosas que el ORM dice y que **solo** se rompen al migrar a PostgreSQL.

Los **tipos ENUM** y los **nombres de restriccion**. Son la misma clase de defecto y
conviene que esten en el mismo fichero: los dos son "el modelo declara algo que el
motor de produccion no acepta y el de pruebas si", y los dos aparecieron el mismo dia,
al escribir las migraciones de las 27 tablas. En los dos casos la causa era lo mismo:
**SQLite es mas permisivo que PostgreSQL**, y todo el esquema del proyecto se ha
verificado siempre contra SQLite.

## Tipos ENUM

Un `SqlEnum` se materializa en PostgreSQL como un tipo con nombre. Si dos columnas
distintas declaran el mismo nombre de tipo con **valores distintos**, la segunda
`CREATE TYPE` falla (o, si se reaplica, se reutiliza el primero y la columna acaba
guardando valores que su enumerado no conoce).

En SQLite no hay ENUM: la columna es un `VARCHAR` con su propio `CHECK`, generado con
sus valores. Por eso las colisiones son invisibles hasta que alguien escribe el
`CREATE TYPE` de la tabla implicada. Las dos que habia (`estado_periodo` y
`estado_exportacion`, cada una declarada por dos tablas con valores distintos)
aparecieron justo asi.

Dos enumerados con el mismo nombre y los mismos valores, en cambio, si pueden compartir
el tipo: es lo que se hace con `tipo_periodo`, que comparten `models.closing.periodo_cerrado`
y `models.fiscal.periodo_fiscal`. El orden de los valores no importa para esto, asi que
la comparacion es de conjuntos.

## Nombres de restriccion

En PostgreSQL los nombres de restriccion son unicos **dentro de cada tabla**: dos
`CONSTRAINT` con el mismo nombre hacen fallar el `CREATE TABLE`. En SQLite no importa.

La causa era la convencion de `base.py`:

    "uq": "uq_%(table_name)s_%(column_0_name)s"

que solo mira la **primera** columna. Una tabla con `UNIQUE (empresa_id, id)` y
`UNIQUE (empresa_id, ejercicio, numero)` recibe `uq_tabla_empresa_id` en las dos, y la
segunda es un duplicado. SPEC-020 declaro cuatro tablas asi y se cerro con 54/54 tareas
y las puertas en verde.

El arreglo es poner `name=` explicito en la restriccion de negocio, que es la que
duplica. La `(empresa_id, id)` se queda con el nombre de la convencion, porque es la
que el resto de las tablas del proyecto ya llaman asi.
"""

from __future__ import annotations

import collections

import sqlalchemy as sa

import models  # noqa: F401  (registra las 109 tablas)
from base import Base


def _enums_por_nombre() -> dict[str, dict[frozenset[str], set[str]]]:
    """`{nombre_del_tipo: {conjunto_de_valores: {columnas que lo usan}}}`."""
    salida: dict[str, dict[frozenset[str], set[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    for tabla in Base.metadata.tables.values():
        for columna in tabla.columns:
            if isinstance(columna.type, sa.Enum):
                clave = frozenset(columna.type.enums)
                salida[columna.type.name][clave].add(f"{tabla.name}.{columna.name}")
    return salida


def test_no_hay_dos_enums_con_el_mismo_nombre_y_valores_distintos() -> None:
    """La puerta que habria parado las dos colisiones.

    El nombre del tipo PostgreSQL es unico. Dos enumerados con el mismo nombre y
    valores distintos no pueden convivir, y el conflicto no se ve hasta que se
    escribe la migracion: en SQLite cada columna lleva su propio `CHECK`.
    """
    colisiones = {
        nombre: sorted(sorted(v) for v in conjuntos)
        for nombre, conjuntos in _enums_por_nombre().items()
        if len(conjuntos) > 1
    }
    assert not colisiones, (
        "tipos ENUM con el mismo nombre y valores distintos. En PostgreSQL un tipo se "
        f"define una vez, asi que la segunda tabla que los use no se podria migrar: "
        f"{colisiones}. Anade el sufijo que toque al `name=` del `SqlEnum` "
        "(como hace `models/budget/periodo_seguimiento.py` con "
        "`periodo_seguimiento_estado`)."
    )


#: Tipos ENUM que comparten varias tablas a proposito, con el motivo de cada uno.
#:
#: Compartir es correcto siempre que los valores coincidan (lo vigila
#: `test_no_hay_dos_enums_con_el_mismo_nombre_y_valores_distintos`). La lista
#: esta escrita a mano a proposito: si aparece un quinto nombre, hay que decidir
#: si el reparto es intencionado, y decidir exige ver la lista.
TIPOS_COMPARTIDOS: dict[str, str] = {
    "actividad_efe": "informe_efe y linea_efe clasifican el mismo bloque (SPEC-027)",
    "tipo_adeudo": "remesa y devolucion comparten el tipo de adeudo (SPEC-020)",
    "tipo_periodo": "periodo_cerrado y periodo_fiscal usan MES/TRIMESTRE (SPEC-028/012)",
    "tipo_retencion_irpf": "factura_linea y retencion comparten la categoria (SPEC-007/024)",
}


def test_los_enums_comparten_tipo_solo_si_tienen_los_mismos_valores() -> None:
    """Compartir tipo entre tablas es correcto; lo que no puede ser es a ciegas.

    Los tipos compartidos son los de `TIPOS_COMPARTIDOS`. El test falla si aparece
    uno nuevo, porque un reparto de enums que no se ha decidido no es un reparto:
    es un nombre que dos clases eligieron igual por casualidad.
    """
    compartidos = {
        nombre
        for nombre, conjuntos in _enums_por_nombre().items()
        if len(conjuntos) == 1
        and len({c for cols in conjuntos.values() for c in cols}) > 1
    }
    assert compartidos == set(TIPOS_COMPARTIDOS), (
        "los tipos ENUM compartidos han cambiado. Si el reparto sigue siendo "
        f"intencionado, actualiza TIPOS_COMPARTIDOS; si no, renombra uno. "
        f"comparte={sorted(compartidos)} declarados={sorted(TIPOS_COMPARTIDOS)}"
    )


def test_todo_enum_del_orm_tiene_nombre_explicito() -> None:
    """Sin `name=`, SQLAlchemy deriva el nombre del nombre de la clase en minusculas.

    Dos clases distintas pueden acabar en el mismo tipo, y el nombre derivado no
    dice de donde viene. Declararlo obliga a decidir.
    """
    sin_nombre = [
        f"{tabla.name}.{columna.name} -> {columna.type!r}"
        for tabla in Base.metadata.tables.values()
        for columna in tabla.columns
        if isinstance(columna.type, sa.Enum) and not columna.type.name
    ]
    assert not sin_nombre, sin_nombre


def test_los_valores_de_un_enum_no_se_repiten() -> None:
    """Un `CREATE TYPE ... AS ENUM` con un valor duplicado es un error de sintaxis.

    `columna.type.enums` es una tupla, no un conjunto: si un valor estuviera
    repetido, la tupla seria mas larga que su conjunto, y el `CREATE TYPE` de la
    migracion reventaria al aplicarse contra PostgreSQL.
    """
    for tabla in Base.metadata.tables.values():
        for columna in tabla.columns:
            if isinstance(columna.type, sa.Enum):
                declarados = tuple(columna.type.enums)
                assert len(declarados) == len(set(declarados)), (
                    f"{tabla.name}.{columna.name} repite valores en "
                    f"{columna.type.name}: {declarados}"
                )


# ---------------------------------------------------------------------------
# Los nombres de restriccion
# ---------------------------------------------------------------------------
#
# En PostgreSQL los nombres de restriccion son unicos **dentro de cada tabla**: dos
# `CONSTRAINT` con el mismo nombre en la misma tabla hacen que el `CREATE TABLE` falle.
# En SQLite no importa, y ahi se creaban todas estas tablas en cada test.
#
# La causa era la convencion de `base.py`:
#
#     "uq": "uq_%(table_name)s_%(column_0_name)s"
#
# que solo mira la **primera** columna. Una tabla con `UNIQUE (empresa_id, id)` y
# `UNIQUE (empresa_id, ejercicio, numero)` recibe `uq_tabla_empresa_id` en las dos, y
# la segunda es un duplicado. SPEC-020 declaro cuatro tablas asi y se cerro con 54/54
# tareas y las puertas en verde; el problema solo aparece al escribir el `CREATE TABLE`
# de PostgreSQL.
#
# El arreglo es poner `name=` explicito en la restriccion de negocio, que es la que
# duplica. La `(empresa_id, id)` se queda con el nombre de la convencion, porque es la
# que el resto de las tablas del proyecto ya llaman asi.


def test_no_hay_dos_restricciones_con_el_mismo_nombre() -> None:
    """Ninguna tabla declara dos restricciones con el mismo nombre.

    Es la puerta que habria parado a SPEC-020, y la que evita repetirla en la
    siguiente spec que escriba dos unicos que empiecen por `empresa_id`.
    """
    import collections

    repetidas: dict[str, list] = {}
    for tabla in Base.metadata.tables.values():
        conteo = collections.Counter(c.name for c in tabla.constraints if c.name)
        for nombre, veces in conteo.items():
            if veces > 1:
                repetidas[f"{tabla.name}.{nombre}"] = sorted(
                    tuple(c.name for c in c.columns)
                    for c in tabla.constraints
                    if c.name == nombre
                )
    assert not repetidas, (
        "restricciones con el mismo nombre dentro de la misma tabla. En PostgreSQL el "
        f"`CREATE TABLE` falla con 'already contains constraint': {repetidas}. Pon "
        "`name=` explicito en la de negocio; la convencion "
        "`uq_%(table_name)s_%(column_0_name)s` solo mira la primera columna, y por eso "
        "colisiona cuando las dos empiezan por `empresa_id`."
    )


def test_los_unicos_de_negocio_no_dependen_del_nombre_derivado() -> None:
    """Un unico de negocio lleva un nombre propio, no el derivado de su primera columna.

    No es una regla estetica. El nombre derivado `uq_<tabla>_<primera_columna>` es el
    que choca cuando dos unicos de la misma tabla empiezan por `empresa_id` (lo vigila
    `test_no_hay_dos_restricciones_con_el_mismo_nombre`), y ademas es un nombre que
    miente: `uq_secuencia_remesa_empresa_id` no es la clave de empresa, es la clave de
    empresa y ejercicio. Leyendolo en un `\\d` de PostgreSQL no se entiende.

    Se exime la clave `(empresa_id, id)`, que es la que el proyecto llama asi en todas
    las tablas y la que las FKs compuestas esperan, y `(tenant_id, id)` de
    `account_plan`, que crea 001_account_plan.sql con ese nombre y **ya esta aplicada**
    (renombrarla exigiria una migracion nueva y no arregla nada).
    """
    import sqlalchemy as sa

    CANONICAS = {("empresa_id", "id"), ("tenant_id", "id")}
    mentirosos: dict[str, str] = {}
    for tabla in Base.metadata.tables.values():
        for c in tabla.constraints:
            if c.__class__ is not sa.UniqueConstraint:
                continue
            columnas = tuple(col.name for col in c.columns)
            if columnas in CANONICAS:
                continue
            if c.name == f"uq_{tabla.name}_{columnas[0]}":
                mentirosos[tabla.name] = f"{c.name} {columnas}"
    assert not mentirosos, (
        f"unicos de negocio con el nombre derivado de su primera columna, que no dice "
        f"lo que abarcan: {mentirosos}. Ponles `name=` explicito con las columnas que "
        "de verdad las definen."
    )
