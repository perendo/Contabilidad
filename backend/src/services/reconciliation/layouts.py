"""Mapa de offsets del fichero de extracto norma 43/19 (SPEC-013).

Layout de referencia (ancho fijo, ISO-8859-1, 100 caracteres por línea). El
parser es configurable por layout para absorber variantes de entidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LONGITUD_LINEA = 100


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
