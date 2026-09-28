"""Cálculo del plan de amortización (SPEC-014 US1, T015).

Prorrateo de períodos parciales según configuración de la empresa
(research D2; convenio documentado en AGENTS.md):

- **mensual** (por defecto): la cuota del mes de alta y del mes de baja se
  considera de **mes completo** (fracción 1).
- **dias**: la primera cuota se prorratea por los días restantes del mes de
  alta y la última por los días transcurridos hasta la fecha de baja.

En ambos métodos la última cuota se ajusta a ``coste - Σ cuotas previas`` para
garantizar la exactitud total y FR-006 (``acumulado <= coste``). Toda la
aritmética es ``Decimal`` con contexto ``ROUND_HALF_EVEN``; prohibido ``float``.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from services.inmovilizado.errores import error

QUANTUM = Decimal("0.0001")
PRORRATEO_DEFAULT = "mensual"
LIMITE_ROWS_REGRESIVO = 1200


def _dias_mes(fecha: date) -> int:
    return calendar.monthrange(fecha.year, fecha.month)[1]


def fraccion_cuota_primera(fecha_alta: date, prorrateo: str = PRORRATEO_DEFAULT) -> Decimal:
    """Fracción aplicada a la cuota del mes de alta (período parcial inicial)."""
    if prorrateo == "dias":
        dias = _dias_mes(fecha_alta)
        return (Decimal(dias - fecha_alta.day + 1) / Decimal(dias)).quantize(
            QUANTUM, ROUND_HALF_EVEN
        )
    if prorrateo != "mensual":
        raise error("prorrateo_invalido", f"Prorrateo desconocido: {prorrateo}")
    return Decimal(1)


def fraccion_cuota_baja(fecha_baja: date, prorrateo: str = PRORRATEO_DEFAULT) -> Decimal:
    """Fracción aplicada a la cuota del mes de baja (período parcial final)."""
    if prorrateo == "dias":
        dias = _dias_mes(fecha_baja)
        return (Decimal(fecha_baja.day) / Decimal(dias)).quantize(QUANTUM, ROUND_HALF_EVEN)
    if prorrateo != "mensual":
        raise error("prorrateo_invalido", f"Prorrateo desconocido: {prorrateo}")
    return Decimal(1)


def cuota_parcial_baja(
    fecha_baja: date,
    cuota_mes: Decimal,
    prorrateo: str = PRORRATEO_DEFAULT,
) -> Decimal:
    """Cuota del mes de baja prorrateada según la configuración de la empresa."""
    return (cuota_mes * fraccion_cuota_baja(fecha_baja, prorrateo)).quantize(
        QUANTUM, ROUND_HALF_EVEN
    )


def avanzar_periodo(ejercicio: int, periodo: int, saltos: int = 1) -> tuple[int, int]:
    """Avanza `saltos` meses naturales desde (ejercicio, periodo)."""
    total = ejercicio * 12 + (periodo - 1) + saltos
    return total // 12, total % 12 + 1


def _cuotas_lineales(restante: Decimal, n: int) -> list[Decimal]:
    base = (restante / Decimal(n)).quantize(QUANTUM, ROUND_HALF_EVEN)
    cuotas = [base] * n
    cuotas[-1] = restante - base * Decimal(n - 1)
    return cuotas


def _cuotas_regresivas(restante: Decimal, n: int, porcentaje: Decimal) -> list[Decimal]:
    percent = (porcentaje / Decimal(100)).quantize(QUANTUM, ROUND_HALF_EVEN)
    cuotas: list[Decimal] = []
    acumulado = Decimal(0)
    residual = restante
    for _ in range(n):
        cuota = (residual * percent).quantize(QUANTUM, ROUND_HALF_EVEN)
        if cuota <= 0 or cuota >= residual:
            cuota = residual
        cuotas.append(cuota)
        acumulado += cuota
        residual = restante - acumulado
        if residual <= 0:
            break
    if sum(cuotas, Decimal(0)) != restante:
        previas = sum(cuotas[:-1], Decimal(0))
        cuotas[-1] = restante - previas
    return cuotas


def distribuir_monto(
    restante: Decimal,
    n: int,
    metodo: str,
    porcentaje: Decimal | None = None,
) -> list[Decimal]:
    """Reparte `restante` en `n` cuotas (mes completo, sin prorrateo inicial)."""
    if restante <= 0:
        raise error("plan_invalido", "No queda importe amortizable por distribuir")
    if n <= 0:
        raise error("plan_invalido", "No hay períodos pendientes en el plan")
    if metodo == "lineal":
        cuotas = _cuotas_lineales(restante, n)
    elif metodo == "regresivo":
        if porcentaje is None:
            raise error("porcentaje_requerido", "El método regresivo exige porcentaje_regresivo")
        cuotas = _cuotas_regresivas(restante, n, porcentaje)
    else:
        raise error("metodo_invalido", f"Método desconocido: {metodo}")
    if any(c <= 0 for c in cuotas):
        raise error("plan_invalido", "El plan genera cuotas no positivas")
    return cuotas


def calcular_plan(
    coste: str | Decimal,
    vida_util: int,
    metodo: str,
    porcentaje: str | Decimal | None,
    fecha_alta: date,
    prorrateo: str = PRORRATEO_DEFAULT,
) -> list[dict]:
    """Devuelve el plan completo ``[{ejercicio, periodo, cuota, acumulado}]``."""
    coste_dec = Decimal(str(coste))
    if not (1 <= vida_util <= 600):
        raise error("vida_util_invalida", "vida_util debe estar entre 1 y 600 períodos")
    if coste_dec <= 0:
        raise error("coste_invalido", "coste_amortizable debe ser mayor que 0")

    if metodo == "lineal":
        n = vida_util
        porcentaje_dec = None
    elif metodo == "regresivo":
        n = LIMITE_ROWS_REGRESIVO
        if porcentaje is None:
            raise error("porcentaje_requerido", "El método regresivo exige porcentaje_regresivo")
        porcentaje_dec = Decimal(str(porcentaje))
        if not (Decimal(0) < porcentaje_dec < Decimal(100)):
            raise error("porcentaje_invalido", "porcentaje_regresivo debe estar entre 0 y 100")
    else:
        raise error("metodo_invalido", f"Método desconocido: {metodo}")

    ejercicio, periodo = fecha_alta.year, fecha_alta.month
    acumulado = Decimal(0)
    filas: list[dict] = []

    if metodo == "lineal":
        base = (coste_dec / Decimal(vida_util)).quantize(QUANTUM, ROUND_HALF_EVEN)
        fraccion_inicial = fraccion_cuota_primera(fecha_alta, prorrateo)
        for i in range(vida_util):
            if acumulado >= coste_dec:
                break
            cuota = base if i > 0 else (base * fraccion_inicial).quantize(QUANTUM, ROUND_HALF_EVEN)
            resto = coste_dec - acumulado
            cuota = min(resto, cuota)
            if cuota <= 0:
                cuota = resto
            acumulado += cuota
            filas.append(
                {"ejercicio": ejercicio, "periodo": periodo, "cuota": cuota, "acumulado": acumulado}
            )
            ejercicio, periodo = avanzar_periodo(ejercicio, periodo)
    else:
        # Simulación natural hasta que el valor residual se agota.
        assert porcentaje_dec is not None
        percent = porcentaje_dec
        residual = coste_dec
        fraccion_inicial = fraccion_cuota_primera(fecha_alta, prorrateo)
        i = 0
        while residual > 0 and i < n:
            cuota = (residual * percent).quantize(QUANTUM, ROUND_HALF_EVEN)
            if i == 0:
                cuota = (cuota * fraccion_inicial).quantize(QUANTUM, ROUND_HALF_EVEN)
            if cuota <= 0 or cuota >= residual:
                cuota = residual
            acumulado += cuota
            residual = coste_dec - acumulado
            filas.append(
                {"ejercicio": ejercicio, "periodo": periodo, "cuota": cuota, "acumulado": acumulado}
            )
            ejercicio, periodo = avanzar_periodo(ejercicio, periodo)
            i += 1
        if residual > 0:
            # Cierre de seguridad: el remanente se absorbe en una fila final.
            acumulado += residual
            filas.append(
                {
                    "ejercicio": ejercicio,
                    "periodo": periodo,
                    "cuota": residual,
                    "acumulado": acumulado,
                }
            )

    if filas and filas[-1]["acumulado"] != coste_dec:
        previas = filas[-1]["acumulado"] - filas[-1]["cuota"]
        filas[-1]["cuota"] = coste_dec - previas
        filas[-1]["acumulado"] = coste_dec

    if any(f["cuota"] <= 0 for f in filas):
        raise error("plan_invalido", "El plan genera cuotas no positivas")
    if any(f["acumulado"] > coste_dec for f in filas):
        raise error("plan_excede_coste", "El plan supera el coste amortizable (FR-006)")
    return [
        {
            "ejercicio": f["ejercicio"],
            "periodo": f["periodo"],
            "cuota": f"{f['cuota']:0.4f}",
            "acumulado": f"{f['acumulado']:0.4f}",
        }
        for f in filas
    ]


def replanear_pendientes(
    coste: str | Decimal,
    metodo: str,
    porcentaje: str | Decimal | None,
    n_pendientes: int,
) -> list[Decimal]:
    """Cuotas para la porción pendiente del plan (edición, constitución II)."""
    coste_dec = Decimal(str(coste))
    if coste_dec <= 0:
        raise error("coste_invalido", "coste_amortizable debe ser mayor que 0")
    porcentaje_dec = Decimal(str(porcentaje)) if porcentaje is not None else None
    if metodo == "regresivo" and porcentaje_dec is None:
        raise error("porcentaje_requerido", "El método regresivo exige porcentaje_regresivo")
    return distribuir_monto(coste_dec, n_pendientes, metodo, porcentaje_dec)