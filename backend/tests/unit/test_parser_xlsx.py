"""Tests del parser del XLSX de banco (SPEC-013, correccion provisional 2026-09-29).

El formato es el que exporta la banca electronica espanola: una hoja con un bloque
de metadatos encima, la tabla de movimientos con las fechas como texto `DD/MM/AAAA`,
el signo **dentro** del importe y una columna `Saldo` con el saldo posterior a cada
movimiento.

El constructor del fichero esta en `extracto_xlsx_support.py` y sus numeros son
inventados a proposito: el XLSX que hay en `Data/` es un extracto real y meterlo en
el repositorio seria un problema de datos personales.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from services.reconciliation.parsers import (
    LayoutError,
    importe_de_celda,
    normalizar_columna,
    parse_extracto,
    parse_xlsx_bancario,
)
from tests.unit.extracto_xlsx_support import IBAN, MOVIMIENTOS, xlsx_banco

CABECERA = [
    "Fecha Operación",
    "Fecha Valor",
    "Concepto",
    "Importe",
    "Divisa",
    "Saldo",
    "Divisa",
    "Código",
    "Número de documento",
    "Referencia 1",
    "Referencia 2",
    "Información adicional",
]


# ---------------------------------------------------------------------------
# Lectura del formato
# ---------------------------------------------------------------------------


def test_el_xlsx_del_banco_se_importa_completo() -> None:
    """El caso que motivo la correccion: el fichero que descarga el banco se lee."""
    dto = parse_xlsx_bancario(xlsx_banco())
    assert len(dto.movimientos) == 4
    assert dto.iban == IBAN.replace(" ", "")
    assert dto.cuenta == ""


def test_el_saldo_inicial_se_deriva_de_la_cadena_de_saldos() -> None:
    """El XLSX no trae saldo inicial: sale de restar el ultimo movimiento al ultimo saldo."""
    dto = parse_xlsx_bancario(xlsx_banco())
    # El banco entrega el mas reciente primero: el ultimo saldo es 2988.74 y el
    # ultimo movimiento (02/01) es un abono de 1125, luego el inicial era 1863.74.
    assert dto.saldo_final == Decimal("4623.7400")
    assert dto.saldo_inicial == Decimal("1863.7400")
    neto = sum(
        (m.importe if m.signo == "H" else -m.importe for m in dto.movimientos), Decimal(0)
    )
    assert neto == dto.saldo_final - dto.saldo_inicial


def test_el_signo_va_dentro_del_importe() -> None:
    dto = parse_xlsx_bancario(xlsx_banco())
    por_concepto = {m.concepto: m for m in dto.movimientos}
    cargo = por_concepto["Traspaso: Traspaso"]
    abono = por_concepto["Abono cliente"]
    assert (cargo.signo, cargo.importe) == ("D", Decimal("595.0000"))
    assert (abono.signo, abono.importe) == ("H", Decimal("1805.0000"))


def test_los_movimientos_quedan_ordenados_del_mas_antiguo_al_mas_reciente() -> None:
    """El banco entrega el mas reciente primero y el extracto se lee al reves."""
    dto = parse_xlsx_bancario(xlsx_banco())
    fechas = [m.fecha_operacion for m in dto.movimientos]
    assert fechas == sorted(fechas)
    assert [m.orden for m in dto.movimientos] == [1, 2, 3, 4]


def test_el_rango_de_fechas_es_el_de_los_movimientos() -> None:
    dto = parse_xlsx_bancario(xlsx_banco())
    assert dto.fecha_inicio == date(2026, 1, 2)
    assert dto.fecha_fin == date(2026, 2, 27)


def test_la_referencia_toma_el_numero_de_documento() -> None:
    dto = parse_xlsx_bancario(xlsx_banco())
    por_concepto = {m.concepto: m for m in dto.movimientos}
    assert por_concepto["Recibo domiciliado"].referencia == "3495913000"


def test_acepta_la_hoja_ordenada_al_contrario() -> None:
    """Un exportador propio entrega lo mas antiguo primero y tambien vale."""
    dto = parse_xlsx_bancario(xlsx_banco(invertido=False))
    assert dto.saldo_inicial == Decimal("1863.7400")
    assert dto.saldo_final == Decimal("4623.7400")


def test_sin_bloque_de_metadatos_tambien_funciona() -> None:
    """La cabecera se busca, no se asume en la fila 1: sin metadatos esta en la 1."""
    dto = parse_xlsx_bancario(xlsx_banco(con_metadatos=False))
    assert len(dto.movimientos) == 4
    assert dto.iban is None


def test_acepta_fechas_como_fecha_real_de_excel() -> None:
    """Si el banco exporta la fecha como fecha y no como texto, tambien se lee."""
    dto = parse_xlsx_bancario(xlsx_banco(fechas_texto=False))
    assert all(m.fecha_operacion == date(2026, 2, 27) for m in dto.movimientos)
    assert len(dto.movimientos) == 4


def test_acepta_una_cabecera_con_acentos_distintos() -> None:
    """La cabecera se compara sin tildes: un banco que las quita no deja de importar."""
    plano = ["Fecha Operacion", "Fecha Valor", "Concepto", "Importe", "Divisa", "Saldo"]
    dto = parse_xlsx_bancario(xlsx_banco(cabecera=plano))
    assert len(dto.movimientos) == 4


def test_el_iban_se_lee_del_bloque_de_metadatos() -> None:
    dto = parse_xlsx_bancario(xlsx_banco())
    assert dto.iban is not None
    assert dto.iban.startswith("ES") and len(dto.iban) == 24


def test_ignora_una_fila_de_totales_al_final() -> None:
    """La columna de saldos se queda en la ultima fila: un pie con totales que no
    tiene fecha no es un movimiento y no puede tumbar la importacion."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    for columna, nombre in enumerate(CABECERA, start=1):
        hoja.cell(row=1, column=columna, value=nombre)
    for desplazamiento, (f_op, f_val, concepto, importe, saldo, codigo, num_doc) in enumerate(
        MOVIMIENTOS
    ):
        r = 2 + desplazamiento
        hoja.cell(row=r, column=1, value=f_op)
        hoja.cell(row=r, column=2, value=f_val)
        hoja.cell(row=r, column=3, value=concepto)
        hoja.cell(row=r, column=4, value=importe)
        hoja.cell(row=r, column=6, value=saldo)
    hoja.cell(row=2 + len(MOVIMIENTOS), column=3, value="TOTALES")
    hoja.cell(row=2 + len(MOVIMIENTOS), column=4, value=0)
    buffer = io.BytesIO()
    libro.save(buffer)
    dto = parse_xlsx_bancario(buffer.getvalue())
    assert len(dto.movimientos) == len(MOVIMIENTOS)


# ---------------------------------------------------------------------------
# Lo que el parser tiene que rechazar
# ---------------------------------------------------------------------------


def test_rechaza_un_saldo_que_no_encaja_con_los_importes() -> None:
    """Un movimiento de mas o de menos deja la cadena de saldos rota, y se dice."""
    roto = list(MOVIMIENTOS)
    roto[1] = (*roto[1][:3], 999.99, roto[1][4], *roto[1][5:])
    with pytest.raises(LayoutError) as exc:
        parse_xlsx_bancario(xlsx_banco(roto))
    assert exc.value.code == "layout_invalido"
    assert exc.value.campo == "saldo"
    assert exc.value.registro > 0


def test_rechaza_un_extracto_que_no_tiene_la_cabecera() -> None:
    otras = ["Columna A", "Columna B", "Columna C"]
    with pytest.raises(LayoutError) as exc:
        parse_xlsx_bancario(xlsx_banco(cabecera=otras))
    assert exc.value.campo == "cabecera"


def test_rechaza_un_extracto_sin_movimientos() -> None:
    libro = openpyxl.Workbook()
    hoja = libro.active
    for columna, nombre in enumerate(CABECERA, start=1):
        hoja.cell(row=1, column=columna, value=nombre)
    buffer = io.BytesIO()
    libro.save(buffer)
    with pytest.raises(LayoutError) as exc:
        parse_xlsx_bancario(buffer.getvalue())
    assert exc.value.campo == "movimientos"


def test_rechaza_un_xlsx_danado() -> None:
    with pytest.raises(LayoutError) as exc:
        parse_xlsx_bancario(b"esto no es un xlsx")
    assert exc.value.campo == "fichero"


def test_rechaza_un_xlsx_vacio() -> None:
    with pytest.raises(LayoutError) as exc:
        parse_xlsx_bancario(b"")
    assert exc.value.campo == "fichero"


def test_rechaza_un_extracto_que_no_esta_en_euros() -> None:
    """Un extracto en dolares importado como si fuera de euros es un extracto falso."""
    with pytest.raises(LayoutError) as exc:
        parse_xlsx_bancario(xlsx_banco(divisa="USD"))
    assert exc.value.code == "divisa_no_soportada"


def test_rechaza_una_fecha_ilegible() -> None:
    datos = list(MOVIMIENTOS)
    datos[0] = ("no es una fecha", *datos[0][1:])
    with pytest.raises(LayoutError) as exc:
        parse_xlsx_bancario(xlsx_banco(datos))
    assert exc.value.campo == "fecha_operacion"


# ---------------------------------------------------------------------------
# Despacho
# ---------------------------------------------------------------------------


def test_el_despacho_reconoce_el_xlsx() -> None:
    assert parse_extracto(xlsx_banco(), "xlsx_bancario").iban is not None


@pytest.mark.parametrize("layout", ["xlsx", "", "XLSX", "csv", "norma43", "banco"])
def test_un_formato_desconocido_se_rechaza_en_vez_de_caer_en_la_norma_43(
    layout: str,
) -> None:
    """Con el despacho de antes, un valor mal escrito acababa en el parser de ancho
    fijo y contestaba 'longitud 22 != 100', que no decia nada del problema real."""
    with pytest.raises(LayoutError) as exc:
        parse_extracto(xlsx_banco(), layout)
    assert exc.value.code == "layout_desconocido"


# ---------------------------------------------------------------------------
# Precision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("celda", "esperado"),
    [
        (-595.0, Decimal("-595.0000")),
        (5281.99, Decimal("5281.9900")),
        (0.07, Decimal("0.0700")),
        (1234, Decimal("1234.0000")),
        ("-595,00", Decimal("-595.0000")),
        ("1.250,50", Decimal("1250.5000")),
        ("1250.50", Decimal("1250.5000")),
        (None, Decimal("0.0000")),
    ],
)
def test_los_importes_siempre_son_decimal_de_cuatro(celda: object, esperado: Decimal) -> None:
    assert importe_de_celda(celda, 9, "importe") == esperado


def test_un_importo_que_no_es_numero_se_rechaza() -> None:
    with pytest.raises(LayoutError):
        importe_de_celda("no es un numero", 9, "importe")


def test_normalizar_columna_ignora_tildes_y_espacios() -> None:
    assert normalizar_columna("Fecha Operación") == "fechaoperacion"
    assert normalizar_columna("  Importe ") == "importe"
    assert normalizar_columna("Número de documento") == "numerodedocumento"
    assert normalizar_columna(None) == ""
