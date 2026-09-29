"""Constructor de un XLSX con la forma del extracto que da un banco (SPEC-013).

Vive en un modulo aparte y no en un test porque lo usan dos: los tests del parser
(`tests/unit/test_parser_xlsx.py`) y los de la importacion
(`tests/integration/test_importacion_xlsx.py`). Importar de un test a otro rompe la
recoleccion de pytest con el modo `prepend`, que es la leccion del proyecto.

**Por que el fichero no se copia a `tests/fixtures/`.** En `Data/` hay un extracto
real, con IBAN y con nombres de terceros de una institucion concreta. Meterlo en el
repositorio es un problema de datos personales que no se deshace borrandolo del
working tree. Lo que se prueba aqui es la **forma** del formato, con numeros
inventados; el fichero real se comprueba a mano y se documenta en `correcciones.md`.
"""

from __future__ import annotations

import io
from datetime import date

import openpyxl

#: Movimientos del extracto de referencia, en el orden en que los entrega el banco
#: (del mas reciente al mas antiguo) con su saldo posterior. Los saldos encadenan
#: de verdad: partiendo de 1863.74, el 02/01 deja 2988.74, el 15/02 llega a
#: 4793.74, el segundo de febrero a 5218.74 y el traspaso del 27 lo baja a 4623.74.
MOVIMIENTOS: list[tuple] = [
    ("27/02/2026", "27/02/2026", "Traspaso: Traspaso", -595.00, 4623.74, "072", None),
    ("27/02/2026", "26/02/2026", "Recibo domiciliado", 425.00, 5218.74, "174", "3495913000"),
    ("15/02/2026", "16/02/2026", "Abono cliente", 1805.00, 4793.74, "071", None),
    ("02/01/2026", "02/01/2026", "Emision remesa SEPA SDD", 1125.00, 2988.74, "173", None),
]

CABECERA: list[str] = [
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

IBAN = "ES91 2100 0418 4502 0005 1332"


def xlsx_banco(
    movimientos: list[tuple] | None = None,
    *,
    cabecera: list[str] | None = None,
    con_metadatos: bool = True,
    divisa: str = "EUR",
    invertido: bool = True,
    fechas_texto: bool = True,
) -> bytes:
    """Construye un XLSX con la forma del extracto del banco.

    Por defecto reproduce lo que hace la banca electronica espanola: un bloque de
    metadatos de siete filas con el titular y el IBAN, la tabla de movimientos a
    partir de la octava, las fechas como texto `DD/MM/AAAA`, los importes como
    numeros con el signo puesto y la columna de saldos encadenada.
    """
    datos = list(movimientos if movimientos is not None else MOVIMIENTOS)
    if not invertido:
        datos = list(reversed(datos))
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "movimientos"
    fila = 1
    if con_metadatos:
        for etiqueta, valor in (
            ("Titular", "Empresa de prueba"),
            ("Saldo disponible", "4.623,74 EUR"),
            ("Cuenta", IBAN),
            ("Retenciones", "0,00 EUR"),
        ):
            hoja.cell(row=fila, column=3, value=etiqueta)
            hoja.cell(row=fila, column=4, value=valor)
            fila += 2
        hoja.cell(row=fila, column=1, value="Movimientos Fecha desde 02/01/2026")
    fila += 2
    for columna, nombre in enumerate(cabecera or CABECERA, start=1):
        hoja.cell(row=fila, column=columna, value=nombre)
    inicio = fila
    for desplazamiento, (f_op, f_val, concepto, importe, saldo, codigo, num_doc) in enumerate(
        datos
    ):
        r = inicio + 1 + desplazamiento
        valor_fecha = f_op if fechas_texto else date(2026, 2, 27)
        valor_fecha_valor = f_val if fechas_texto else date(2026, 2, 27)
        hoja.cell(row=r, column=1, value=valor_fecha)
        hoja.cell(row=r, column=2, value=valor_fecha_valor)
        hoja.cell(row=r, column=3, value=concepto)
        hoja.cell(row=r, column=4, value=importe)
        hoja.cell(row=r, column=5, value=divisa)
        hoja.cell(row=r, column=6, value=saldo)
        hoja.cell(row=r, column=7, value=divisa)
        hoja.cell(row=r, column=8, value=codigo)
        hoja.cell(row=r, column=9, value=num_doc)
        hoja.cell(row=r, column=10, value="")
        hoja.cell(row=r, column=11, value="")
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
