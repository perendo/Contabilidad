"""El esquema de PostgreSQL real, comparado con lo que declaran los modelos.

Opt-in, como `test_pg_schema.py`: se omite si no hay `TEST_DATABASE_URL`.

## Por que este fichero existe

`test_migrations.py` comprueba el inventario **de ficheros**: que las migraciones
declaradas esten en la lista y que el orden por dependencias cuadre. Es una puerta
que lee la declaracion. Y una puerta que lee la declaracion no ve lo que falta:
un modelo sin migracion no aparece en el inventario, asi que no hay nada que
faltara y el guard pasa en verde.

Eso no es hipotetico. SPEC-013 se cerro con 54/54 tareas y las seis puertas en
verde, y sus seis tablas no existian en PostgreSQL. `POST /api/v1/extractos`
devolvia 500 y toda la superficie de conciliacion era inservible. Los tests no lo
vieron porque crean el esquema con `Base.metadata.create_all`, que si sabe lo que
el ORM declara; las migraciones no lo saben y nadie se lo preguntaba a las dos.

Este guard hace esa pregunta: cruzando los `__tablename__` de `src/models/` con las
columnas que PostgreSQL tiene de verdad.

## Lo que mira, y lo que no

Mira, por columna: que la tabla exista, que la columna exista, el tipo, si admite
nulo y el valor por defecto.

**No** mira claves foraneas, indices, unicidades parciales, enums ni triggers.
Hay guards especificos para parte de eso (`test_pg_schema.py` para los triggers,
`test_migrations.py` para el orden), pero no hay todavia uno que compare FKs e
indices entre modelo y esquema. Es un limite conocido y esta escrito aqui para que
nadie lo lea como una garantia que no da.

## La deuda

Lo que si difiere y se admite a sabias esta en `tests/esquema_deuda.py`, y son dos
reglas: solo puede encogerse, y no puede mentir en ninguna direccion. Este fichero
las vigila **contra la base de verdad**, no contra los ficheros.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from esquema_deuda import COLUMNAS_INCONSISTENTES, TABLAS_SIN_MIGRACION, deuda_completa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from db.esquema import comparar_con_modelos, solo_reales
from db.migrate import archivos_ordenados

URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not URL, reason="TEST_DATABASE_URL no configurada (se omite PostgreSQL)"
)


@pytest.fixture
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Aplica las migraciones (idempotentes) y abre la base ya migrada.

    Se aplican aqui a proposito, y no para "dejar la base como debe": para que la
    comparacion sea **migraciones contra modelos**, que es la pregunta que
    importa. Si solo se leyera el estado actual, el guard responderia a "esta la
    base al dia", y esa es otra pregunta, mas debil.
    """
    assert URL is not None
    engine = create_async_engine(URL)
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        for archivo in archivos_ordenados():
            await driver.execute(archivo.read_text(encoding="utf-8"))
    yield engine
    await engine.dispose()


async def _diferencias(engine: AsyncEngine):
    """Todas las diferencias entre el modelo y la base, con todos los modelos cargados."""
    import models  # noqa: F401  (registra las 109 tablas en el metadata)
    from base import Base

    async with engine.connect() as conn:
        return await comparar_con_modelos(conn, Base.metadata)


# ---------------------------------------------------------------------------
# La puerta
# ---------------------------------------------------------------------------


async def test_el_esquema_no_se_aparta_de_los_modelos(pg_engine: AsyncEngine) -> None:
    """Ninguna diferencia real fuera de la deuda declarada.

    Esta es la puerta que habria parado SPEC-013: una tabla nueva en `src/models/`
    sin migracion que la cree es exactamente esto.
    """
    diferencias = solo_reales(await _diferencias(pg_engine))
    conocidas = deuda_completa()
    nuevas = {(d.tabla, d.columna) for d in diferencias} - conocidas
    assert not nuevas, (
        f"el esquema de PostgreSQL no coincide con los modelos en {len(nuevas)} "
        f"sitio(s) que no son deuda declarada:\n"
        + "\n".join(f"  {d}" for d in diferencias if (d.tabla, d.columna) in nuevas)
        + "\n\nSi la tabla es nueva, escribe su migracion en backend/migrations/ y "
        "anadela a ORDEN_PREFERENTE y a ESPERADAS. Si no va a tenerla todavia, "
        "declaerala en tests/esquema_deuda.py (esa lista solo puede encogerse)."
    )


# ---------------------------------------------------------------------------
# La deuda no puede mentir
# ---------------------------------------------------------------------------


async def test_la_deuda_de_tablas_sigue_siendo_deuda(pg_engine: AsyncEngine) -> None:
    """Todo lo que `TABLAS_SIN_MIGRACION` nombra, sigue faltando de verdad.

    Sin esta, la lista podria quedarse YEARS desactualizada y el guard de arriba
    seguiria en verde: una lista de deuda que miente deja de ser una lista.
    """
    diferencias = solo_reales(await _diferencias(pg_engine))
    faltan = {(d.tabla, d.columna) for d in diferencias}
    ya_arregladas = {(t, None) for t in TABLAS_SIN_MIGRACION} - faltan
    assert not ya_arregladas, (
        "ya no son deuda, borralas de TABLAS_SIN_MIGRACION para que el guard sea "
        f"mas estricto: {sorted(t for t, c in ya_arregladas if t)}"
    )


async def test_la_deuda_de_columnas_sigue_siendo_deuda(pg_engine: AsyncEngine) -> None:
    """Lo mismo para las columnas inconsistentes."""
    diferencias = solo_reales(await _diferencias(pg_engine))
    faltan = {(d.tabla, d.columna) for d in diferencias}
    ya_arregladas = set(COLUMNAS_INCONSISTENTES) - faltan
    assert not ya_arregladas, (
        "ya no son deuda, borralas de COLUMNAS_INCONSISTENTES: "
        f"{sorted(ya_arregladas)}"
    )


# ---------------------------------------------------------------------------
# Que la comparacion se este haciendo de verdad
# ---------------------------------------------------------------------------


async def test_la_comparacion_esta_contando_algo(pg_engine: AsyncEngine) -> None:
    """Contra una base vacia el guard de arriba pasaria sin comprobar nada.

    Esta comprueba que el comparador ve la base. Sin ella, un `information_schema`
    mal escrito daria cero diferencias, cero nuevas, y el guard en verde sobre una
    base que no se ha mirado.
    """
    import models  # noqa: F401
    from base import Base
    from db.esquema import describir_base, describir_modelos

    declarados = describir_modelos(Base.metadata)
    async with pg_engine.connect() as conn:
        existentes = await describir_base(conn)

    declaradas, reales = set(declarados), set(existentes)
    assert len(declaradas) > 80, sorted(declaradas)
    assert len(reales) > 80, sorted(reales)

    # El conjunto de lo que falta, exactamente. Igualdad de conjuntos y no una
    # resta de numeros: la resta daria el mismo resultado con la base vacia, con
    # una tabla duplicada, o con cualquier error que se compense con otro.
    assert declaradas - reales == TABLAS_SIN_MIGRACION, {
        "faltan y no son deuda": sorted((declaradas - reales) - TABLAS_SIN_MIGRACION),
        "deuda que ya no esta": sorted(TABLAS_SIN_MIGRACION - (declaradas - reales)),
    }

    # Y el otro lado de la regla: la base puede tener tablas que ningun modelo
    # declara. `schema_migrations` es una de ellas, y lleva ahi desde que
    # `db.migrate` empenzo a registrar las versiones aplicadas. Que aparezca aqui
    # no es un fallo: es la regla de "la base puede declarar mas" funcionando.
    assert "schema_migrations" in reales - declaradas, sorted(reales - declaradas)
async def test_la_deuda_no_crece(pg_engine: AsyncEngine) -> None:
    """La alarma: la deuda de tablas **nunca puede pasar de 27**.

    No comprueba el numero exacto, y es a proposito. La primera version de este test
    hacia `assert len(TABLAS_SIN_MIGRACION) == 27` y fallo en cuanto se migraron las
    cinco del grupo 1: un guard que falla cuando la deuda **baja**: esta castigando
    el progreso y hay que arreglarlo antes de que tapara el defecto real, que es que
    suba.

    El encogimiento ya lo vigila `test_la_deuda_de_tablas_sigue_siendo_deuda`, que
    comprueba contra la base que lo que queda en la lista sigue faltando de verdad.
    Aqui solo va el techo.
    """
    assert len(TABLAS_SIN_MIGRACION) <= 27, (
        f"la deuda de tablas ha CRECIDO a {len(TABLAS_SIN_MIGRACION)} (el techo es 27, "
        "el punto de partida del 2026-09-29). Anade la migracion de la tabla nueva, o "
        "si de verdad no va a tenerla, declaralo aqui sabiendo que la lista solo puede "
        "encogerse y que este es el numero del que se sale para siempre"
    )


def test_el_numero_de_tablas_del_orm_no_crece() -> None:
    """109 es el numero que tenia el ORM cuando se midio la deuda.

    Si sube, hay un modelo nuevo, y lo habitual es que venga sin migracion: que es
    justo lo que esta puerta existe para cazar. No es un tope que deba bajarse a
    proposito (borrar un maestro si es lo correcto), pero si conviene verlo.
    """
    import models  # noqa: F401
    from base import Base

    declaradas = len(Base.metadata.tables)
    assert declaradas == 109, (
        f"el ORM declara {declaradas} tablas y tenia 109. Si anadiste una, comprueba "
        "que tiene migracion; si la quitaste, esta cifra esta bien y hay que "
        "actualizarla aqui y en TABLAS_SIN_MIGRACION"
    )

