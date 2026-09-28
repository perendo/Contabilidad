"""Parser de importaciones CSV/JSON (SPEC-025 T023).

Casos contractuales: CSV esc3 exacto, delimitador `;`, cabecera obligatoria,
errores por fila, JSON mal formado y decodificacion latin.
"""

from __future__ import annotations

import pytest

from services.catalog.errores import CatalogoError
from services.catalog.importacion_catalogo import (
    decodificar,
    parsear_csv,
    parsear_json,
)

CSV_ES3 = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "renombrado,4300,Clientes euros,430,4310\n"
    "alta,4310,Clientes pagos,431,\n"
)


def test_csv_esc3_exacto():
    operaciones = parsear_csv(CSV_ES3)
    assert len(operaciones) == 2
    assert operaciones[0] == {
        "operacion": "renombrado",
        "codigo": "4300",
        "nombre": "Clientes euros",
        "padre_codigo": "430",
        "destino_codigo": "4310",
    }
    assert operaciones[1]["operacion"] == "alta"
    assert operaciones[1]["codigo"] == "4310"
    assert operaciones[1]["destino_codigo"] is None
    assert operaciones[1]["padre_codigo"] == "431"


def test_csv_delimitador_punto_y_coma():
    contenido = (
        "operacion;codigo;nombre;padre_codigo;destino_codigo\n"
        "baja;4300;Clientes;;\n"
    )
    operaciones = parsear_csv(contenido)
    assert operaciones == [
        {
            "operacion": "baja",
            "codigo": "4300",
            "nombre": "Clientes",
            "padre_codigo": None,
            "destino_codigo": None,
        }
    ]


def test_csv_cabecera_incompleta():
    with pytest.raises(CatalogoError) as exc:
        parsear_csv("codigo,nombre\n4300,Clientes\n")
    assert exc.value.code == "fichero_invalido"
    assert exc.value.status_code == 422


def test_csv_fila_invalida_reportada():
    contenido = (
        "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
        "modificar,4300,Clientes,430,\n"
        "alta,4310,Clientes pagos,431,\n"
    )
    with pytest.raises(CatalogoError) as exc:
        parsear_csv(contenido)
    assert exc.value.code == "fila_invalida"
    errores = exc.value.extra["errores"]
    assert len(errores) == 1
    assert errores[0]["fila"] == 2
    assert "alta" in errores[0]["motivo"]


def test_csv_vacio():
    with pytest.raises(CatalogoError) as exc:
        parsear_csv("\n  \n")
    assert exc.value.code == "fichero_invalido"


def test_csv_sin_operaciones():
    with pytest.raises(CatalogoError) as exc:
        parsear_csv("operacion,codigo\n")
    assert exc.value.code == "fichero_invalido"


def test_json_valido():
    datos = parsear_json(
        '{"codigo_version": "NORMA-2026", "fecha_inicio": "2026-01-01",'
        ' "operaciones": [{"operacion": "alta", "codigo": "4310",'
        ' "nombre": "x", "padre_codigo": "431"}]}'
    )
    assert datos.codigo_version == "NORMA-2026"
    assert datos.fecha_inicio.isoformat() == "2026-01-01"
    assert datos.operaciones[0].destino_codigo is None
    assert datos.mapeo == []


def test_json_invalido():
    with pytest.raises(CatalogoError) as exc:
        parsear_json("{no es json")
    assert exc.value.code == "fichero_invalido"
    assert exc.value.status_code == 422


def test_json_no_objeto():
    with pytest.raises(CatalogoError) as exc:
        parsear_json('[{"operacion": "alta"}]')
    assert exc.value.code == "fichero_invalido"


def test_json_errores_por_campo():
    with pytest.raises(CatalogoError) as exc:
        parsear_json(
            '{"codigo_version": "X", "fecha_inicio": "2026-01-01",'
            ' "operaciones": [{"operacion": "modificar", "codigo": "4300"}]}'
        )
    assert exc.value.code == "fichero_invalido"
    errores = exc.value.extra["errores"]
    assert errores[0]["campo"].startswith("operaciones")


def test_decodificar_utf8_con_bom():
    contenido = "operacion,c\u00f3digo\n".encode("utf-8-sig")
    assert decodificar(contenido) == "operacion,c\u00f3digo\n"


def test_decodificar_iso_8859_15():
    contenido = "nombre,clientes a\u00f1o".encode("iso-8859-15")
    texto = decodificar(contenido)
    assert "a\u00f1o" in texto
