"""Tests SPEC-005 Foundational (T009/T013): parseo CSV y rechazo de formato."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.importexport.parseador import (
    ParseError,
    agrupar_por_asiento,
    parsear_csv,
)

CABECERA = "fecha;numero_asiento;concepto;cuenta;debe;haber\n"


def _csv(*lineas: str, sep: str = ";") -> bytes:
    cabecera = CABECERA if sep == ";" else CABECERA.replace(";", sep)
    return (cabecera + "\n".join(lineas)).encode("utf-8")


def test_agrupacion_por_numero_asiento() -> None:
    datos = _csv(
        "2026-05-01;1;Venta;4300;100,00;0",
        "2026-05-01;1;Venta;5720;0;100,00",
        "2026-05-02;2;Compra;6000;50,00;0",
        "2026-05-02;2;Compra;5720;0;50,00",
    )
    filas = parsear_csv(datos, 10)
    grupos = agrupar_por_asiento(filas)
    assert set(grupos) == {"1", "2"}
    assert len(grupos["1"]) == 2
    assert filas[0].debe == Decimal("100.00")


def test_deteccion_separador_tab_y_coma() -> None:
    tab = "fecha\tnumero_asiento\tconcepto\tcuenta\tdebe\thaber\n2026-05-01\t1\tV\t4300\t1.00\t0\n"
    assert len(parsear_csv(tab.encode("utf-8"), 10)) == 1
    coma = "fecha,numero_asiento,concepto,cuenta,debe,haber\n2026-05-01,1,V,4300,1.00,0\n"
    assert len(parsear_csv(coma.encode("utf-8"), 10)) == 1


def test_encoding_iso88591() -> None:
    datos = (
        "fecha;numero_asiento;concepto;cuenta;debe;haber\n"
        "2026-05-01;1;Compra;6000;10,00;0\n"
    ).encode("iso-8859-1")
    filas = parsear_csv(datos, 10)
    assert filas[0].concepto == "Compra"


def test_cabecera_incompleta_rechazada() -> None:
    datos = b"fecha;cuenta;debe\n2026-05-01;4300;10,00\n"
    with pytest.raises(ParseError) as exc:
        parsear_csv(datos, 10)
    assert exc.value.code == "columnas_faltantes"


def test_debe_haber_vacios_son_cero() -> None:
    filas = parsear_csv(_csv("2026-05-01;1;V;4300;;;"), 10)
    assert filas[0].debe == Decimal(0)
    assert filas[0].haber == Decimal(0)


def test_binario_corrupto_rechazado() -> None:
    with pytest.raises(ParseError):
        parsear_csv(b"\x00\x01\x02\xff\xfe", 10)
