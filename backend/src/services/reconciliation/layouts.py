"""Layouts de extracto bancario admitidos (SPEC-013).

Dos cosas distintas viven aqui, y conviene no confundirlas:

1. `LayoutNorma43`, el **mapa de offsets** del fichero de ancho fijo (100 caracteres
   por linea, ISO-8859-1). Es una guia de bytes: donde empieza y donde acaba cada
   campo del registro `01`, `21`/`22` y `98`.
2. `LAYOUTS`, el **catalogo de nombres** que el cliente puede enviar en el campo
   `layout` del formulario de importacion. El catalogo es la unica lista de
   formatos soportados, y la comparten la API, el parser y los tests: un formato
   que no este aqui no se puede importar, y un formato que se anyada al parser y
   se olvide de la API existe pero no se puede pedir.

El tercero (`xlsx_bancario`) no tiene offsets porque no es de ancho fijo: es una
hoja de calculo. Lo que declara son las **columnas** que tienen que existir, y lo
que se busca es la fila de cabecera en lugar de asumir que esta en la primera.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LONGITUD_LINEA = 100

#: Formatos de extracto que la importacion acepta, con la etiqueta que ve el
#: usuario. El orden es el del desplegable del frontend.
LAYOUTS: dict[str, str] = {
    "norma_43_1919": "Norma 43/19",
    "csv_normalizado": "CSV normalizado",
    "xlsx_bancario": "XLSX de banco (Santander y similares)",
}

#: Formatos que no son texto: el prefijo de la API y el `accept` del navegador se
#: derivan de aqui en vez de estar escritos a mano en tres sitios.
LAYOUTS_XLSX = ("xlsx_bancario",)


@dataclass(frozen=True)
class LayoutNorma43:
    """Slices (start, end) sobre cada tipo de registro."""

    longitud_linea: int = LONGITUD_LINEA
    cabecera: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "codigo": (0, 2),
            "referencia": (2, 18),
            "fecha_datos": (18, 26),
            "cuenta": (26, 60),
            "saldo_inicial": (60, 76),
            "saldo_final": (76, 92),
        }
    )
    operacion: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "codigo": (0, 2),
            "concepto_cod": (2, 6),
            "fecha_operacion": (6, 14),
            "fecha_valor": (14, 22),
            "concepto": (22, 70),
            "importe": (70, 86),
            "referencia": (86, 100),
        }
    )
    control: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "codigo": (0, 2),
            "n_operaciones": (2, 8),
            "suma": (8, 24),
        }
    )


LAYOUT_NORMA_43 = LayoutNorma43()

CODIGOS_CABECERA = ("01",)
CODIGOS_DEBITO = ("21",)
CODIGOS_CREDITO = ("22",)
CODIGO_CONTROL = "98"

# ---------------------------------------------------------------------------
# Columnas del XLSX de banco
# ---------------------------------------------------------------------------

#: Columnas **obligatorias** del XLSX, ya normalizadas (ver `normalizar_columna`):
#: sin acentos, sin espacios y en minusculas. `fechaoperacion` y `importe` son los
#: datos del movimiento; `saldo` es lo que permite **derivar** el saldo inicial, y
#: sin el el extracto no se podria cuadrar contra nada.
COLUMNAS_XLSX_OBLIGATORIAS = ("fechaoperacion", "importe", "saldo")

#: Columnas **opcionales**. Se toman si estan, y se dejan a `None` si no.
COLUMNAS_XLSX_OPCIONALES = (
    "fechavalor",
    "concepto",
    "codigo",
    "numerodedocumento",
    "referencia1",
    "referencia2",
)

#: Cuantas filas se barren buscando la cabecera. El fichero del banco lleva un
#: bloque de metadatos encima (titular, IBAN, saldos y el rango de fechas) que no
#: tiene anchura fija garantizada, asi que la cabecera se **busca** en vez de
#: asumir la fila 1. Con 40 filas de margen sobra de sobra sin recorrer la hoja.
FILAS_BUSQUEDA_CABECERA = 40

