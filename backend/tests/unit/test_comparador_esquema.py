"""El comparador de esquema, probado con datos inventados.

Un guard que no se ha visto fallar no es un guard. Estas pruebas construyen tablas
de mentira y comprueban que el comparador las detecta, una a una, y que separa
las diferencias de verdad de las que son la misma cosa escrita de dos maneras.

No necesitan base de datos: `comparar` es una funcion pura sobre dos diccionarios.
"""

from __future__ import annotations

from db.esquema import (
    GRAVEDAD_EQUIVALENTE,
    Columna,
    Tabla,
    comparar,
    solo_reales,
)


def _col(nombre: str, tipo: str = "VARCHAR(50)", nullable: bool = False, defecto=None) -> Columna:
    return Columna(nombre=nombre, tipo=tipo, nullable=nullable, defecto=defecto)


def _tabla(nombre: str, columnas: list[Columna]) -> Tabla:
    return Tabla(nombre=nombre, columnas={c.nombre: c for c in columnas})


def _iguales() -> dict[str, Tabla]:
    columnas = [_col("id", "UUID"), _col("empresa_id", "BIGINT"), _col("nombre")]
    return {"tercero": _tabla("tercero", columnas)}


# ---------------------------------------------------------------------------
# Detecta lo que tiene que detectar
# ---------------------------------------------------------------------------


def test_no_hay_diferencias_cuando_coinciden() -> None:
    assert comparar(_iguales(), _iguales()) == []


def test_detecta_una_tabla_que_no_existe() -> None:
    diferencias = comparar(_iguales(), {})
    assert len(diferencias) == 1
    assert diferencias[0].tabla == "tercero"
    assert "NO EXISTE" in diferencias[0].detalle
    assert diferencias[0].es_real


def test_detecta_una_columna_que_no_existe() -> None:
    declarado = _tabla("tercero", [_col("id", "UUID"), _col("nueva")])
    diferencias = comparar({"tercero": declarado}, _iguales())
    assert len(diferencias) == 1
    assert diferencias[0].columna == "nueva"
    assert "NO EXISTE" in diferencias[0].detalle
    assert diferencias[0].es_real


def test_detecta_un_tipo_distinto() -> None:
    base = _tabla("tercero", [_col("id", "UUID"), _col("empresa_id", "BIGINT"),
                              _col("nombre", "VARCHAR(200)")])
    diferencias = comparar(_iguales(), {"tercero": base})
    assert len(diferencias) == 1
    assert "tipo" in diferencias[0].detalle
    assert "VARCHAR(50)" in diferencias[0].detalle
    assert diferencias[0].es_real


def test_detecta_nulabilidad_distinta() -> None:
    base = _tabla("tercero", [_col("id", "UUID"), _col("empresa_id", "BIGINT"),
                              _col("nombre", nullable=True)])
    diferencias = comparar(_iguales(), {"tercero": base})
    assert len(diferencias) == 1
    assert "nulabilidad" in diferencias[0].detalle
    assert diferencias[0].es_real


def test_detecta_un_defecto_distinto() -> None:
    base = _tabla("tercero", [_col("id", "UUID"), _col("empresa_id", "BIGINT"),
                              _col("nombre", defecto="OTRO")])
    diferencias = comparar(_iguales(), {"tercero": base})
    assert len(diferencias) == 1
    assert "valor por defecto" in diferencias[0].detalle
    assert diferencias[0].es_real


def test_detecta_varias_diferencias_en_la_misma_tabla() -> None:
    base = _tabla("tercero", [_col("id", "INTEGER"), _col("empresa_id", "BIGINT"),
                              _col("nombre", nullable=True)])
    assert len(comparar(_iguales(), {"tercero": base})) == 2


# ---------------------------------------------------------------------------
# No se equivoca de lado
# ---------------------------------------------------------------------------


def test_la_base_puede_tener_mas_tablas_de_las_declaradas() -> None:
    """Una tabla de mas en la base no es un fallo: la migracion puede declararla
    aunque ningun modelo la use todavia."""
    extra = _tabla("tabla_que_nadie_declara", [_col("id", "UUID")])
    declaradas = dict(_iguales())
    declaradas["extra"] = extra
    assert comparar(_iguales(), declaradas) == []


def test_la_base_puede_tener_mas_columnas_de_las_declaradas() -> None:
    """Idem con columnas: una FK o un campo auxiliar de mas no rompe a la aplicacion."""
    base = _tabla("tercero", [_col("id", "UUID"), _col("empresa_id", "BIGINT"),
                              _col("nombre"), _col("columna_extra")])
    assert comparar(_iguales(), {"tercero": base}) == []


# ---------------------------------------------------------------------------
# La clasificacion: esto es lo que separa un guard util de uno apagado
# ---------------------------------------------------------------------------


def test_un_tipo_equivalente_no_es_real() -> None:
    """VARCHAR(64) frente a CHAR(64): los dos guardan 64 caracteres."""
    declarado = _tabla("exportacion", [_col("sha256", "VARCHAR(64)")])
    base = _tabla("exportacion", [_col("sha256", "CHAR(64)")])
    diferencias = comparar({"exportacion": declarado}, {"exportacion": base})
    assert len(diferencias) == 1
    assert not diferencias[0].es_real
    assert diferencias[0].gravedad == GRAVEDAD_EQUIVALENTE
    assert solo_reales(diferencias) == []


def test_json_y_jsonb_no_son_diferencia() -> None:
    declarado = _tabla("subvencion", [_col("partidas", "JSON")])
    base = _tabla("subvencion", [_col("partidas", "JSONB")])
    assert solo_reales(comparar({"subvencion": declarado}, {"subvencion": base})) == []


def test_un_entero_estrecho_no_es_diferencia() -> None:
    declarado = _tabla("plantilla", [_col("version_actual", "BIGINT")])
    base = _tabla("plantilla", [_col("version_actual", "INTEGER")])
    assert solo_reales(comparar({"plantilla": declarado}, {"plantilla": base})) == []


def test_un_defecto_numericamente_igual_no_es_diferencia() -> None:
    """PostgreSQL reduce DEFAULT 0.0000 a '0'. Es el mismo numero."""
    declarado = _tabla("cobro_medio", [_col("importe_comision", defecto="0.0000")])
    base = _tabla("cobro_medio", [_col("importe_comision", defecto="0")])
    assert solo_reales(comparar({"cobro_medio": declarado}, {"cobro_medio": base})) == []


def test_un_defecto_por_funcion_no_es_diferencia() -> None:
    """El modelo dice uuid4() y la base lo resuelve sola. No hay nada que comparar."""
    declarado = _tabla("tercero", [_col("id", "UUID", defecto="callable:uuid4")])
    base = _tabla("tercero", [_col("id", "UUID", defecto="gen_random_uuid()")])
    assert solo_reales(comparar({"tercero": declarado}, {"tercero": base})) == []


def test_un_defecto_ausente_no_se_disfraza_de_equivalente() -> None:
    """Si el modelo dice 0 y la base no tiene defecto, eso SI es real.

    Es el caso de `manifiesto_exportacion.n_bloques`, encontrado al pasar el
    comparador. Que no se disfraze de equivalente es lo que lo deja visible.
    """
    declarado = _tabla("manifiesto_exportacion", [_col("n_bloques", "INTEGER", defecto="0")])
    base = _tabla("manifiesto_exportacion", [_col("n_bloques", "INTEGER")])
    diferencias = solo_reales(comparar({"manifiesto_exportacion": declarado},
                                      {"manifiesto_exportacion": base}))
    assert len(diferencias) == 1
    assert "valor por defecto" in diferencias[0].detalle


# ---------------------------------------------------------------------------
# El lado del modelo, con modelos de verdad
# ---------------------------------------------------------------------------
#
# Los tests de arriba usan columnas inventadas con el tipo ya escrito, y eso no
# alcanza para la parte que mas fallos ha dado: leer el tipo que declara el modelo.
# Con `str()`, un `Uuid` sale como `CHAR(32)` y un
# `JSON().with_variant(JSONB, "postgresql")` sale como `JSON`: los dos son el mismo
# tipo escrito en el dialecto que NO es el de produccion. Sin esta seccion, el
# comparador daria cientos de falsas y dejaria de servir para nada.


def test_el_tipo_de_un_modelo_se_lee_con_el_dialecto_de_postgres() -> None:
    """Un `Uuid` declarado en el modelo es `UUID` en PostgreSQL, no `CHAR(32)`."""
    import models.treasury  # noqa: F401  (registra las tablas)
    from base import Base
    from db.esquema import _tipo_de_modelo

    columna = Base.metadata.tables["extracto_bancario"].columns["id"]
    assert _tipo_de_modelo(columna) == "UUID"


def test_una_columna_json_con_variante_se_lee_como_jsonb() -> None:
    """`JSON().with_variant(JSONB, "postgresql")` es `JSONB` en produccion."""
    import models.treasury  # noqa: F401
    from base import Base
    from db.esquema import _tipo_de_modelo

    columna = Base.metadata.tables["prevision_tesoreria"].columns["plan_manual"]
    assert _tipo_de_modelo(columna) == "JSONB"


def test_un_numeric_no_empieza_a_pisar_por_el_espacio() -> None:
    """`NUMERIC(18, 4)` y `NUMERIC(18,4)` son el mismo tipo."""
    import models.treasury  # noqa: F401
    from base import Base
    from db.esquema import _tipo_de_modelo

    columna = Base.metadata.tables["extracto_bancario"].columns["saldo_inicial"]
    assert _tipo_de_modelo(columna) == "NUMERIC(18,4)"


def test_un_defecto_de_enumerado_se_compara_por_su_valor() -> None:
    """El modelo dice `EstadoAlerta.abierta`; lo que hay en la base es `abierta`.

    Sin tomar el `.value`, cada columna con enumerado por defecto marca una
    diferencia que no existe.
    """
    import models.treasury  # noqa: F401
    from base import Base
    from db.esquema import _defecto_de_modelo

    columna = Base.metadata.tables["alerta_conciliacion"].columns["estado"]
    assert _defecto_de_modelo(columna) == "abierta"

