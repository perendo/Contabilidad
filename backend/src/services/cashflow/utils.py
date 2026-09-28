"""Funciones puras de tesoreria: cuantizacion, saldos y buckets (SPEC-027 T009).

Todo en `Decimal` cuantizado a 4 decimales (SC-005); prohibido `float`. Los
buckets son la agregacion de `research.md` D2: la granularidad elegida
(`dia`/`semana`/`mes`) define la clave de agrupacion y el saldo de cada
bucket es `saldo_inicial + S(movimientos de los buckets anteriores y del propio)`.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

__all__ = [
    "CUATRO_DECIMALES",
    "CUENTAS_TESORERIA",
    "GRUPO_TESORERIA",
    "Bucket",
    "agrupar_en_buckets",
    "c4",
    "clave_bucket",
    "enumerar_buckets",
    "es_cuenta_tesoreria",
    "fmt",
    "primer_dia_bucket",
    "saldo_banco",
    "siguiente_bucket",
    "suma_decimal",
    "total_variacion",
]

CUATRO_DECIMALES = Decimal("0.0001")

#: Prefijo PGC del grupo 5 (tesoreria): 570 Caja, 572 Bancos c/c.
GRUPO_TESORERIA = "5"
CUENTAS_TESORERIA: tuple[str, ...] = ("570", "572", "575", "576")


def c4(valor: Decimal | int | str) -> Decimal:
    """Cuantiza a 4 decimales con redondeo comercial (SC-005)."""
    return Decimal(str(valor)).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def fmt(valor: Decimal | int | str | None) -> str:
    """Formato de salida canonico `"1250.0000"` (contrato: nunca coma flotante)."""
    return f"{c4(valor or 0):0.4f}"


def suma_decimal(valores: Iterable[Any]) -> Decimal:
    """Suma de importes a 4 decimales. `None`/vacio cuenta como cero.

    Acepta `Decimal`, `int`, `str` o `None` (los saldos recien asignados de una
    fila ORM pueden venir sin cuantizar). Nunca devuelve `float`.
    """
    total = Decimal(0)
    for valor in valores:
        if valor is None:
            continue
        total += Decimal(str(valor))
    return c4(total)


def es_cuenta_tesoreria(codigo: str | None) -> bool:
    """True si el codigo pertenece al grupo 5 del PGC (research D1)."""
    return bool(codigo) and str(codigo).strip()[:1] == GRUPO_TESORERIA


def saldo_banco(movimientos: Iterable[Decimal | int | str | None]) -> Decimal:
    """Saldo de tesoreria: `S(debe) - S(haber)` de las lineas del grupo 5.

    Recibe las diferencias ya restadas para no depender del signo con el que
    el llamante exprese cada apunte.
    """
    return suma_decimal(movimientos)


class Bucket:
    """Bucket de proyeccion: una clave de la granularidad y sus flujos."""

    __slots__ = ("cobros", "fecha", "pagos")

    def __init__(self, fecha: date) -> None:
        self.fecha = fecha
        self.cobros = Decimal(0)
        self.pagos = Decimal(0)

    @property
    def neto(self) -> Decimal:
        """Cobros menos pagos del bucket, en `Decimal` a 4 decimales."""
        return c4(self.cobros - self.pagos)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuracion
        return f"Bucket({self.fecha.isoformat()}, cobros={self.cobros}, pagos={self.pagos})"


def primer_dia_bucket(fecha: date, granularidad: str) -> date:
    """Fecha inicial del bucket que contiene a `fecha` (research D2).

    - `dia`: la propia fecha.
    - `semana`: el lunes de su semana ISO.
    - `mes`: el dia 1 del mes.
    """
    if granularidad == "dia":
        return fecha
    if granularidad == "semana":
        return fecha - timedelta(days=fecha.weekday())
    if granularidad == "mes":
        return fecha.replace(day=1)
    raise ValueError(f"granularidad no soportada: {granularidad!r}")


def clave_bucket(fecha: date, granularidad: str) -> date:
    """Alias semantico de `primer_dia_bucket` usado por US1 y US3."""
    return primer_dia_bucket(fecha, granularidad)


def siguiente_bucket(fecha: date, granularidad: str) -> date:
    """Primer dia del bucket siguiente (para enumerar buckets sin huecos)."""
    if granularidad == "dia":
        return fecha + timedelta(days=1)
    if granularidad == "semana":
        return fecha + timedelta(days=7)
    if granularidad == "mes":
        ultimo = calendar.monthrange(fecha.year, fecha.month)[1]
        return fecha.replace(day=1) + timedelta(days=ultimo)
    raise ValueError(f"granularidad no soportada: {granularidad!r}")


def enumerar_buckets(desde: date, hasta: date, granularidad: str) -> list[date]:
    """Todos los buckets del rango inclusivo `desde..hasta` (sin huecos)."""
    inicio = primer_dia_bucket(desde, granularidad)
    buckets: list[date] = []
    cursor = inicio
    while cursor <= hasta:
        buckets.append(cursor)
        cursor = siguiente_bucket(cursor, granularidad)
    return buckets


def agrupar_en_buckets(
    movimientos: Iterable[dict[str, Any]], granularidad: str
) -> list[Bucket]:
    """Agrupa movimientos `{fecha, tipo, importe}` en buckets de la granularidad.

    Los movimientos sin `fecha` se ignoran (ya fueron reportados como
    excluidos con motivo `sin_fecha` por `recuperar_movimientos_proyectables`).
    """
    acumulado: dict[date, Bucket] = {}
    for movimiento in movimientos:
        fecha = movimiento.get("fecha_prevista")
        if fecha is None:
            continue
        clave = clave_bucket(fecha, granularidad)
        bucket = acumulado.get(clave)
        if bucket is None:
            bucket = Bucket(clave)
            acumulado[clave] = bucket
        importe = Decimal(str(movimiento.get("importe") or 0))
        if movimiento.get("tipo") == "pago":
            bucket.pagos += importe
        else:
            bucket.cobros += importe
    for bucket in acumulado.values():
        bucket.cobros = c4(bucket.cobros)
        bucket.pagos = c4(bucket.pagos)
    return [acumulado[clave] for clave in sorted(acumulado)]


def total_variacion(buckets: Iterable[Bucket]) -> Decimal:
    """`S(cobros - pagos)` de los buckets: variacion neta proyectada."""
    return c4(sum((b.neto for b in buckets), Decimal(0)))
