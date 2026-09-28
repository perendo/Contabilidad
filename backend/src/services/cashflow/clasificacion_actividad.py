"""Clasificacion de cuentas por bloque de actividad del EFE (SPEC-027 T009/D4).

Regla por defecto (research D4), sobre el primer digito del codigo PGC:

- **operativa**: grupos 6 (gastos), 7 (ingresos) y 5 (tesoreria).
- **inversion**: grupo 2 (inmovilizado) y grupo 8 (subsidios/amortizaciones de
  inmovilizado) por su naturaleza de actividad de inversion.
- **financiacion**: grupo 1 (patrimonio neto), grupo 9 (ingresos/gastos
  financieros) y las deudas de los grupos 16 (deudas a corto plazo) y 17
  (deudas a largo plazo).

El usuario puede reclasificar una cuenta antes de formular el EFE; ese
override se respeta siempre (`LineaEFE.override_usuario = true`). Funcion
pura: no toca la sesion ni devuelve `float`.
"""

from __future__ import annotations

__all__ = [
    "GRUPOS_FINANCIACION",
    "GRUPOS_INVERSION",
    "GRUPOS_OPERATIVA",
    "clasificar_bloque",
    "es_bloque",
    "grupos_de",
]

GRUPOS_OPERATIVA: frozenset[str] = frozenset({"5", "6", "7"})
GRUPOS_INVERSION: frozenset[str] = frozenset({"2", "8"})
GRUPOS_FINANCIACION: frozenset[str] = frozenset({"1", "9", "16", "17"})


def grupos_de(codigo: str | None) -> str:
    """Grupo PGC de una cuenta a partir de su codigo (`"6"`, `"57"`, `"16"`).

    Para los codigos de tres o mas digitos devuelve los dos primeros, de modo
    que `16`/`17` (deudas) se reconocen y `57` (tesoreria) tambien. Los codigos
    de cuatro digitos del PGC puro (`1600`) siguen devolviendo `"16"`.
    """
    if not codigo:
        return ""
    texto = str(codigo).strip()
    if len(texto) >= 2 and texto[:2].isdigit():
        return texto[:2]
    return texto[:1]


def clasificar_bloque(codigo_cuenta: str | None) -> str:
    """Bloque de actividad de una cuenta: operativa/inversion/financiacion.

    Las cuentas fuera de los grupos con regla (0, 3, 4, vacio o codigo no
    numerico) caen en **operativa**: es el bloque por defecto del PGC y evita
    descuadres por cuentas sin clasificacion explicita.
    """
    grupos = grupos_de(codigo_cuenta)
    if grupos in GRUPOS_INVERSION or grupos[:1] in GRUPOS_INVERSION:
        return "inversion"
    if grupos in GRUPOS_FINANCIACION or grupos[:1] in GRUPOS_FINANCIACION:
        return "financiacion"
    if grupos[:1] in GRUPOS_OPERATIVA:
        return "operativa"
    return "operativa"


def es_bloque(bloque: str) -> bool:
    """True si `bloque` es uno de los tres bloques validos del EFE."""
    return bloque in ("operativa", "inversion", "financiacion")
