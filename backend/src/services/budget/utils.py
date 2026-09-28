"""Funciones puras del modulo de presupuestos (SPEC-026).

T008: la convencion de signos de `research.md` D2 vive aqui y se reutiliza en
US2 (seguimiento) y US3 (informe y cierre). Todo en `Decimal` cuantizado a 4
decimales (SC-005); prohibido `float`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "CUATRO_DECIMALES",
    "CUATRO_DECIMALES_RATIO",
    "GRUPO_GASTO",
    "GRUPO_INGRESO",
    "c4",
    "c4_ratio",
    "calcular_desviacion_absoluta",
    "calcular_desviacion_relativa",
    "calcular_real",
    "cuenta_grupo",
    "grupo_de_cuenta",
    "tiene_mas_de_4_decimales",
]

CUATRO_DECIMALES = Decimal("0.0001")
CUATRO_DECIMALES_RATIO = Decimal("0.0001")

GRUPO_GASTO = 6
GRUPO_INGRESO = 7

#: Limite del ratio `NUMERIC(7,4)`; se satura en lugar de romper la columna.
RATIO_MAXIMO = Decimal("999.9999")
RATIO_MINIMO = Decimal("-999.9999")


def c4(valor: Decimal | int | str) -> Decimal:
    """Cuantiza a 4 decimales con redondeo comercial (SC-005)."""
    return Decimal(str(valor)).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def c4_ratio(valor: Decimal | int | str) -> Decimal:
    """Cuantiza un ratio a 4 decimales y lo satura al rango de `NUMERIC(7,4)`."""
    ratio = Decimal(str(valor)).quantize(CUATRO_DECIMALES_RATIO, rounding=ROUND_HALF_UP)
    if ratio > RATIO_MAXIMO:
        return RATIO_MAXIMO
    if ratio < RATIO_MINIMO:
        return RATIO_MINIMO
    return ratio


def cuenta_grupo(codigo: str | None) -> int:
    """Primer digito del codigo PGC como grupo (0 si el codigo no es numerico)."""
    if not codigo:
        return 0
    cabeza = codigo.strip()[:1]
    return int(cabeza) if cabeza.isdigit() else 0


def grupo_de_cuenta(codigo: str | None) -> int:
    """Alias explicito de `cuenta_grupo` para los servicios de desviacion."""
    return cuenta_grupo(codigo)


def calcular_real(
    grupo: int, importe_debe: Decimal, importe_haber: Decimal
) -> Decimal:
    """Real del periodo aplicando la convencion de signos D2.

    - grupo 6 (gastos): ``SUM(Debe)``
    - grupo 7 (ingresos): ``SUM(Haber)``
    - resto de grupos: ``SUM(Debe) - SUM(Haber)``

    Funcion pura: no toca la sesion, siempre devuelve `Decimal` a 4 decimales.
    """
    debe = Decimal(str(importe_debe or 0))
    haber = Decimal(str(importe_haber or 0))
    if grupo == GRUPO_GASTO:
        return c4(debe)
    if grupo == GRUPO_INGRESO:
        return c4(haber)
    return c4(debe - haber)


def calcular_desviacion_absoluta(
    importe_real: Decimal, importe_presupuestado: Decimal
) -> Decimal:
    """Desviacion absoluta D2: ``real - presupuesto`` (positivo = sobregasto)."""
    return c4(Decimal(str(importe_real)) - Decimal(str(importe_presupuestado)))


def calcular_desviacion_relativa(
    importe_real: Decimal, importe_presupuestado: Decimal
) -> Decimal | None:
    """Desviacion relativa D2/D4.

    ``(real - presupuesto) / |presupuesto|``; ``None`` si el presupuesto es 0
    (dividir entre cero no tiene sentido financiero y la columna es NULL).
    """
    presupuesto = Decimal(str(importe_presupuestado))
    if presupuesto == 0:
        return None
    ratio = calcular_desviacion_absoluta(importe_real, presupuesto) / abs(presupuesto)
    return c4_ratio(ratio)


def tiene_mas_de_4_decimales(valor: str | float | Decimal) -> bool:
    """True si la representacion decimal excede 4 decimales (SC-005)."""
    texto = str(valor).strip().replace(" ", "")
    if not texto:
        return False
    if texto.count(".") != 1:
        return False
    _, decimales = texto.split(".")
    return len(decimales) > 4
