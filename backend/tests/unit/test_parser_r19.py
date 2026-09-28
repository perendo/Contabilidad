"""R19/C19 parser tests (T041, T041a).

Extrae código/motivo/importe/importe_gastos/recibo_ref de un fichero AEB
cuaderno 19; normaliza códigos de hasta 10 caracteres (MD01, AC04, R-CUST);
conserva el código externo original en el identificador para trazabilidad.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.remittance.refund_r19 import (
    FormatoRetornoError,
    normalizar_codigo,
    parsear_retorno_aeb19,
    parsear_retorno_r19,
)


def _linea(
    codigo: str,
    clave: str,
    recibo_ref: str,
    fecha: str,
    importe_cents: str,
    gastos_cents: str,
    motivo: str,
) -> bytes:
    cuerpo = (
        "3"
        + codigo.ljust(10)
        + clave.ljust(2)
        + recibo_ref.ljust(12)
        + fecha
        + importe_cents.rjust(12, "0")
        + gastos_cents.rjust(12, "0")
        + motivo.ljust(40)
    )
    return (cuerpo.encode("ISO-8859-15") + b"\r\n")


def _fichero(lineas: list[bytes]) -> bytes:
    return b"".join(lineas)


def test_parseo_registro_tipo_3():
    contenido = _fichero(
        [
            (
                b"1ACME                                          20261001"
                b"0000000150000000000100000000000000000000000000000000"
                b"00000000000000000000000000000000000000000000000000  \r\n"
            ),
            _linea(
                "MD06", "RV", "R-REVERSAL", "20261005",
                "15000", "500", "Mandato rechazado",
            ),
            (
                b"5R0000000150000000000100000000000000000000000000000000"
                b"00000000000000000000000000000000000000000000000000  \r\n"
            ),
        ]
    )
    entradas = parsear_retorno_r19(contenido)
    assert len(entradas) == 1
    entra = entradas[0]
    assert entra.codigo == "MD06"
    assert entra.clave == "RV"
    assert entra.recibo_ref == "R-REVERSAL"
    assert entra.fecha_cargo.isoformat() == "2026-10-05"
    assert entra.importe == Decimal("150.0000")
    assert entra.importe_gastos == Decimal("5.0000")
    assert entra.motivo == "Mandato rechazado"
    assert "MD06" in entra.identificador_externo
    assert "15000" in entra.identificador_externo


def test_codigos_de_hasta_10_caracteres():
    contenido = _fichero(
        [
            _linea(
                "AC04", "DV", "REC-AC04", "20261005",
                "10000", "0", "IBAN inválido",
            ),
            _linea(
                "R-CUST", "DV", "REC-CUST", "20261006",
                "20000", "100", "Rechazado por deudor",
            ),
        ]
    )
    entradas = parsear_retorno_r19(contenido)
    codigos = [e.codigo for e in entradas]
    assert codigos == ["AC04", "R-CUST"]
    assert entradas[0].recibo_ref == "REC-AC04"
    assert entradas[1].importe_gastos == Decimal("1.00")


def test_normalizacion_minusculas_y_espacios():
    assert normalizar_codigo("md06") == "MD06"
    assert normalizar_codigo("  r-cust  ") == "R-CUST"
    assert len(normalizar_codigo("R-CUST")) <= 10


def test_parseo_c19_comparte_layout_y_conserva_tipo():
    entrada = parsear_retorno_aeb19(
        _linea("AC04", "BV", "REC-C19", "20261005", "10000", "0", "Baja"),
        tipo="C19",
    )[0]
    assert entrada.tipo == "C19"
    assert entrada.identificador_externo.startswith("C19:AC04:")


def test_tipo_retorno_invalido_rechazado():
    with pytest.raises(FormatoRetornoError):
        parsear_retorno_aeb19(b"", tipo="C18")


def test_ignora_registros_no_tipo_3():
    contenido = _fichero(
        [
            b"2BANCO RECEPTOR\r\n",
            _linea(
                "AM05", "DV", "REC-AM05", "20261005",
                "10000", "0", "Adendo no autorizado",
            ),
            b"9CIERRE\r\n",
        ]
    )
    entradas = parsear_retorno_r19(contenido)
    assert len(entradas) == 1
    assert entradas[0].codigo == "AM05"


def test_encoding_latin1_con_acentos():
    contenido = _linea(
        "MD02", "BV", "REC-MD02", "20261005",
        "10000", "0", "CUENTA ERRÓNEA",
    )
    entrada = parsear_retorno_r19(contenido)[0]
    assert entrada.motivo == "CUENTA ERRÓNEA"


def test_registro_demasiado_corto_rechazado():
    with pytest.raises(FormatoRetornoError):
        parsear_retorno_r19(b"3MD0\r\n")


def test_fecha_invalida_rechazada():
    with pytest.raises(FormatoRetornoError):
        parsear_retorno_r19(_linea("MD01", "DV", "R-X", "20261399", "10000", "0", "x"))


def test_importe_no_numerico_rechazado():
    with pytest.raises(FormatoRetornoError):
        parsear_retorno_r19(_linea("MD01", "DV", "R-X", "20261005", "AB000", "0", "x"))