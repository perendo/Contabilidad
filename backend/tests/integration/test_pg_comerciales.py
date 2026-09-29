"""Contrato PostgreSQL del grupo 1: terceros y facturacion.

Opt-in, como `test_pg_schema.py`: se omite si no hay `TEST_DATABASE_URL`.

Que prueba y por que hace falta. `test_esquema_completo.py` comprueba que las tablas
**existen y coinciden con el modelo**. Este fichero comprueba lo otro: que las
**restricciones muerden**. Son cosas distintas, y una ronda que solo inserta filas
validas pasaria igual con `empresa_id` de adonde, que es el defecto que mas caro sale
en multi-tenancy.

Lo que se comprueba, en concreto:

1. Una factura con linea entra y se lee, y los `NUMERIC(18,4)` conservan los cuatro
   decimales (la constitucion prohibe `float` para dinero).
2. Las cuatro FKs compuestas de `factura` rechazan una referencia de otra empresa.
   Esto es la constitucion III en la base: una factura de la empresa A no puede
   colgar de la serie, del tercero o del asiento de la empresa B.
3. Los CHECK del modelo rechazan lo que el servicio tambien rechaza: un tercero que
   no es cliente ni proveedor, una linea de cantidad cero, un descuento del 150 %.
4. El UNIQUE `(empresa_id, serie_id, ejercicio, numero)` mantiene la correlatividad
   sin huecos, y `numero` NULL en los borradores no choca con el (NULL no colisiona).

**Limpia lo que crea.** Estas cinco tablas no tienen trigger de inmutabilidad, asi que
el `DELETE` funciona; `audit_log` es WORM y no se toca, y eso es lo que tiene que ser.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from db.migrate import archivos_ordenados

URL = os.getenv("TEST_DATABASE_URL")

#: Dos empresas reales de la base de pruebas. No se crean aqui: sembrar una empresa
#: dispara el trigger que le crea el PGC entero y la matriz de permisos, y para
#: comprobar FKs solo hacen falta dos filas.
EMPRESA_A = 1
EMPRESA_B = 2

pytestmark = pytest.mark.skipif(
    not URL, reason="TEST_DATABASE_URL no configurada (se omite PostgreSQL)"
)


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    assert URL is not None
    engine = create_async_engine(URL)
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        for archivo in archivos_ordenados():
            await driver.execute(archivo.read_text(encoding="utf-8"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def escenario(pg_engine: AsyncEngine):
    """Maestros de las dos empresas, y todo lo creado se borra al terminar.

    Crea un tercero y una serie por empresa, mas una factura en **cada** empresa. La
    factura de la empresa B existe para poder atacar sus lineas desde la A: sin ella
    la prueba de intrusion no probaria nada, porque apuntar una linea a la factura de
    la propia empresa es una linea legitima que la base acepta.
    """
    ids = {
        "t_a": uuid.uuid4(),
        "t_b": uuid.uuid4(),
        "s_a": uuid.uuid4(),
        "s_b": uuid.uuid4(),
        "f_a": uuid.uuid4(),
        "f_b": uuid.uuid4(),
    }
    async with pg_engine.begin() as c:
        for key, empresa in (("t_a", EMPRESA_A), ("t_b", EMPRESA_B)):
            await c.execute(
                text(
                    "INSERT INTO tercero (id, empresa_id, nombre, nif, es_cliente, es_proveedor) "
                    "VALUES (:id, :e, :n, :nif, true, false)"
                ),
                {"id": ids[key], "e": empresa, "n": f"Prueba {empresa}",
                 "nif": f"T{empresa}{uuid.uuid4().hex[:6]}"},
            )
        for key, empresa, codigo in (("s_a", EMPRESA_A, "P1"), ("s_b", EMPRESA_B, "P2")):
            await c.execute(
                text(
                    "INSERT INTO serie_factura (id, empresa_id, codigo, nombre, prefijo, sufijo) "
                    "VALUES (:id, :e, :c, :n, :c, '')"
                ),
                {"id": ids[key], "e": empresa, "c": codigo + uuid.uuid4().hex[:4],
                 "n": f"Serie {codigo}"},
            )
        for key, empresa, serie, tercero in (
            ("f_a", EMPRESA_A, "s_a", "t_a"),
            ("f_b", EMPRESA_B, "s_b", "t_b"),
        ):
            await c.execute(
                text(
                    "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, "
                    "tipo, tercero_id, importe_base, importe_iva, importe_total, estado) "
                    "VALUES (:id, :e, :s, 1, 2026, DATE '2026-01-15', 'VENTA', :t, "
                    "100.0000, 21.0000, 121.0000, 'emitida')"
                ),
                {"id": ids[key], "e": empresa, "s": ids[serie], "t": ids[tercero]},
            )
    try:
        yield ids
    finally:
        async with pg_engine.begin() as c:
            await c.execute(text("DELETE FROM factura_linea WHERE empresa_id IN (:a, :b)"),
                            {"a": EMPRESA_A, "b": EMPRESA_B})
            await c.execute(text("DELETE FROM factura WHERE empresa_id IN (:a, :b)"),
                            {"a": EMPRESA_A, "b": EMPRESA_B})
            await c.execute(text("DELETE FROM serie_factura WHERE empresa_id IN (:a, :b)"),
                            {"a": EMPRESA_A, "b": EMPRESA_B})
            await c.execute(text("DELETE FROM tercero WHERE empresa_id IN (:a, :b)"),
                            {"a": EMPRESA_A, "b": EMPRESA_B})


async def _rechaza(pg_engine: AsyncEngine, sql: str, params: dict) -> str:
    """Ejecuta algo que deberia fallar y devuelve su **SQLSTATE**. Falla si no falla.

    Se comprueba el SQLSTATE y no el nombre de la clase de Python porque el codigo es
    el contrato estable del propio PostgreSQL, y el nombre de la clase no lo es. Peor
    aun, hay que llegar a el: el encadenado es

        sqlalchemy.exc.IntegrityError
          -> .orig = sqlalchemy.dialects.postgresql.asyncpg.IntegrityError
            -> .orig.__cause__ = asyncpg.exceptions.CheckViolationError

    asi que `type(exc.orig).__name__` devuelve `IntegrityError` y parece que la
    prueba no ha comprobado nada. La primera version hacia exactamente eso.

    Codigos que usa esta fichero:
      23514 check_violation          23503 foreign_key_violation
      23505 unique_violation         22P02 invalid_text_representation
    """
    with pytest.raises((IntegrityError, DBAPIError)) as info:
        async with pg_engine.begin() as c:
            await c.execute(text(sql), params)
    return str(getattr(info.value.orig, "sqlstate", "") or "")


#: Traduccion de los SQLSTATE a su nombre, para que los mensajes se lean.
SQLSTATE = {
    "23514": "check_violation",
    "23503": "foreign_key_violation",
    "23505": "unique_violation",
    "22P02": "invalid_text_representation",
}


# ---------------------------------------------------------------------------
# 1. Entra y sale
# ---------------------------------------------------------------------------


async def test_una_factura_con_linea_se_guarda_y_se_lee(pg_engine, escenario) -> None:
    linea = uuid.uuid4()
    async with pg_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO factura_linea (id, empresa_id, factura_id, line_no, descripcion, "
                "cantidad, precio_unitario, base, tipo_iva, cuota_iva) "
                "VALUES (:id, 1, :f, 1, 'Producto', 1.0000, 100.0000, 100.0000, 21.00, 21.0000)"
            ),
            {"id": linea, "f": escenario["f_a"]},
        )
    async with pg_engine.connect() as c:
        total, iva = (
            await c.execute(
                text("SELECT importe_total::text, importe_iva::text FROM factura WHERE id = :i"),
                {"i": escenario["f_a"]},
            )
        ).first()
        n = (
            await c.execute(
                text("SELECT count(*) FROM factura_linea WHERE factura_id = :i"),
                {"i": escenario["f_a"]},
            )
        ).scalar()
    assert total == "121.0000" and iva == "21.0000", (total, iva)
    assert n == 1, n


async def test_los_enums_se_leen(pg_engine, escenario) -> None:
    async with pg_engine.connect() as c:
        estado = (
            await c.execute(
                text("SELECT estado::text FROM serie_factura WHERE id = :i"),
                {"i": escenario["s_a"]},
            )
        ).scalar()
        tipo = (
            await c.execute(
                text("SELECT tipo::text FROM factura WHERE id = :i"),
                {"i": escenario["f_a"]},
            )
        ).scalar()
    assert estado == "activa", estado
    assert tipo == "VENTA", tipo


# ---------------------------------------------------------------------------
# 2. La constitution III, en la base
# ---------------------------------------------------------------------------


async def test_una_factura_no_puede_colgar_de_la_serie_de_otra_empresa(
    pg_engine, escenario
) -> None:
    """FK compuesta (empresa_id, serie_id)."""
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, tipo, "
        "tercero_id) VALUES (:id, 1, :s, 90, 2026, DATE '2026-03-01', 'VENTA', :t)",
        {"id": uuid.uuid4(), "s": escenario["s_b"], "t": escenario["t_a"]},
    )
    assert motivo == "23503", SQLSTATE.get(motivo, motivo)


async def test_una_factura_no_puede_colgar_del_tercero_de_otra_empresa(
    pg_engine, escenario
) -> None:
    """FK compuesta (empresa_id, tercero_id)."""
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, tipo, "
        "tercero_id) VALUES (:id, 1, :s, 91, 2026, DATE '2026-03-02', 'VENTA', :t)",
        {"id": uuid.uuid4(), "s": escenario["s_a"], "t": escenario["t_b"]},
    )
    assert motivo == "23503", SQLSTATE.get(motivo, motivo)


async def test_una_rectificativa_no_puede_colgar_de_la_original_de_otra_empresa(
    pg_engine, escenario
) -> None:
    """FK compuesta (empresa_id, factura_original_id).

    Es la que hace que el encadenamiento de rectificativas no pueda cruzar empresas.
    Si fuese de una sola columna a la PK, una rectificativa de la empresa A podria
    apuntar a la original de la B y el historico de la factura quedaria partido en dos.
    """
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, tipo, "
        "tercero_id, factura_original_id) "
        "VALUES (:id, 1, :s, 92, 2026, DATE '2026-03-03', 'RECTIFICATIVA', :t, :o)",
        {"id": uuid.uuid4(), "s": escenario["s_a"], "t": escenario["t_a"],
         "o": escenario["f_b"]},
    )
    assert motivo == "23503", SQLSTATE.get(motivo, motivo)


async def test_una_rectificativa_de_la_misma_empresa_si_se_admite(pg_engine, escenario) -> None:
    """La mitad que no se prueba a proposito: que el caso bueno tambien pase.

    Una FK que rechazase todo tambien pasaria los tests de arriba.
    """
    rect = uuid.uuid4()
    async with pg_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, tipo, "
                "tercero_id, factura_original_id) "
                "VALUES (:id, 1, :s, 93, 2026, DATE '2026-03-04', 'RECTIFICATIVA', :t, :o)"
            ),
            {"id": rect, "s": escenario["s_a"], "t": escenario["t_a"],
             "o": escenario["f_a"]},
        )
    async with pg_engine.connect() as c:
        encontrada = (
            await c.execute(text("SELECT count(*) FROM factura WHERE id = :i"), {"i": rect})
        ).scalar()
    assert encontrada == 1
    async with pg_engine.begin() as c:
        await c.execute(text("DELETE FROM factura WHERE id = :i"), {"i": rect})


async def test_una_linea_no_puede_colgar_de_la_factura_de_otra_empresa(
    pg_engine, escenario
) -> None:
    """FK compuesta (empresa_id, factura_id) de `factura_linea`."""
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura_linea (id, empresa_id, factura_id, descripcion, cantidad, "
        "precio_unitario) VALUES (:id, 1, :f, 'Intrusa', 1.0000, 1.0000)",
        {"id": uuid.uuid4(), "f": escenario["f_b"]},
    )
    assert motivo == "23503", SQLSTATE.get(motivo, motivo)


# ---------------------------------------------------------------------------
# 3. Los CHECK
# ---------------------------------------------------------------------------


async def test_un_tercero_tiene_que_ser_cliente_o_proveedor(pg_engine) -> None:
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO tercero (id, empresa_id, nombre, es_cliente, es_proveedor) "
        "VALUES (:id, 1, 'No es nadie', false, false)",
        {"id": uuid.uuid4()},
    )
    assert motivo == "23514", SQLSTATE.get(motivo, motivo)


async def test_un_tercero_que_es_las_dos_cosas_si_se_admite(pg_engine) -> None:
    """El caso bueno del CHECK anterior."""
    tid = uuid.uuid4()
    async with pg_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO tercero (id, empresa_id, nombre, nif, es_cliente, es_proveedor) "
                "VALUES (:id, 1, 'Cliente y proveedor', :nif, true, true)"
            ),
            {"id": tid, "nif": f"D{uuid.uuid4().hex[:8]}"},
        )
    async with pg_engine.begin() as c:
        await c.execute(text("DELETE FROM tercero WHERE id = :i"), {"i": tid})


async def test_una_linea_no_puede_tener_cantidad_cero(pg_engine, escenario) -> None:
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura_linea (id, empresa_id, factura_id, descripcion, cantidad, "
        "precio_unitario) VALUES (:id, 1, :f, 'Cero', 0.0000, 1.0000)",
        {"id": uuid.uuid4(), "f": escenario["f_a"]},
    )
    assert motivo == "23514", SQLSTATE.get(motivo, motivo)


async def test_una_linea_no_puede_tener_precio_cero(pg_engine, escenario) -> None:
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura_linea (id, empresa_id, factura_id, descripcion, cantidad, "
        "precio_unitario) VALUES (:id, 1, :f, 'Gratis', 1.0000, 0.0000)",
        {"id": uuid.uuid4(), "f": escenario["f_a"]},
    )
    assert motivo == "23514", SQLSTATE.get(motivo, motivo)


async def test_una_linea_no_puede_tener_un_descuento_del_150(pg_engine, escenario) -> None:
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura_linea (id, empresa_id, factura_id, descripcion, cantidad, "
        "precio_unitario, porcentaje_descuento) "
        "VALUES (:id, 1, :f, 'Imposible', 1.0000, 1.0000, 150.00)",
        {"id": uuid.uuid4(), "f": escenario["f_a"]},
    )
    assert motivo == "23514", SQLSTATE.get(motivo, motivo)


async def test_un_tipo_de_factura_que_no_existe_no_entra(pg_engine, escenario) -> None:
    """El enum `factura_tipo` no admite 'TRASPASO'.

    Nota: PostgreSQL lanza `InvalidTextRepresentationError`, que es un `DataError` y
    **no** un `IntegrityError`. La primera version de esta prueba solo recogia
    `IntegrityError` y dio por hecho que no rechazaba, cuando si que hacia.
    """
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, tipo, "
        "tercero_id) VALUES (:id, 1, :s, 94, 2026, DATE '2026-03-05', 'TRASPASO', :t)",
        {"id": uuid.uuid4(), "s": escenario["s_a"], "t": escenario["t_a"]},
    )
    assert motivo == "22P02", SQLSTATE.get(motivo, motivo)


# ---------------------------------------------------------------------------
# 4. Correlatividad
# ---------------------------------------------------------------------------


async def test_no_hay_dos_facturas_con_el_mismo_numero_de_serie(pg_engine, escenario) -> None:
    motivo = await _rechaza(
        pg_engine,
        "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, tipo, "
        "tercero_id) VALUES (:id, 1, :s, 1, 2026, DATE '2026-02-01', 'VENTA', :t)",
        {"id": uuid.uuid4(), "s": escenario["s_a"], "t": escenario["t_a"]},
    )
    assert motivo == "23505", SQLSTATE.get(motivo, motivo)


async def test_hay_borradores_sin_numero_y_no_chocan(pg_engine, escenario) -> None:
    """`numero` es NULL en los borradores, y NULL no colisiona en un UNIQUE normal.

    Es lo que permite tener cuantos borradores se quiera sin numero. Si aqui se
    rechazara, la app no podria guardar ni un borrador.
    """
    async with pg_engine.begin() as c:
        for _ in range(3):
            await c.execute(
                text(
                    "INSERT INTO factura (id, empresa_id, serie_id, numero, ejercicio, fecha, "
                    "tipo, tercero_id, estado) "
                    "VALUES (:id, 1, :s, NULL, 2026, DATE '2026-04-01', 'VENTA', :t, 'borrador')"
                ),
                {"id": uuid.uuid4(), "s": escenario["s_a"], "t": escenario["t_a"]},
            )
    async with pg_engine.begin() as c:
        await c.execute(
            text("DELETE FROM factura WHERE empresa_id = 1 AND estado = 'borrador'")
        )
