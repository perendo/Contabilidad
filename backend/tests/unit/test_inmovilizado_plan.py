"""Tests pure del plan de amortización (SPEC-014 T015/T016).

Cubren lineal/regresivo, exactitud total (FR-006: acumulado nunca supera el
coste), último ajuste, y el prorrateo de períodos parciales (mensual/dias)
resuelto en SPEC-014 (research D2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.inmovilizado.errores import InmovilizadoError
from services.inmovilizado.plan import (
    avanzar_periodo,
    calcular_plan,
    cuota_parcial_baja,
    fraccion_cuota_baja,
    fraccion_cuota_primera,
    replanear_pendientes,
)


def _suma_filas(plan: list[dict]) -> Decimal:
    return sum((Decimal(f["cuota"]) for f in plan), Decimal(0))


def test_plan_lineal_60_cuotas() -> None:
    plan = calcular_plan("15000.0000", 60, "lineal", None, date(2026, 10, 1))
    assert len(plan) == 60
    assert all(Decimal(f["cuota"]) == Decimal("250.0000") for f in plan)
    assert plan[-1]["acumulado"] == "15000.0000"


def test_plan_lineal_ultima_ajustada() -> None:
    plan = calcular_plan("10000.0000", 3, "lineal", None, date(2026, 1, 1))
    cuotas = [Decimal(f["cuota"]) for f in plan]
    assert cuotas == [Decimal("3333.3333"), Decimal("3333.3333"), Decimal("3333.3334")]
    assert _suma_filas(plan) == Decimal("10000.0000")


def test_plan_no_excede_coste() -> None:
    for metodo, coste, vida, pct in (
        ("lineal", "15000.0000", 60, None),
        ("lineal", "9999.9900", 7, None),
        ("regresivo", "20000.0000", 48, "25.00"),
        ("regresivo", "1200.0000", 12, "33.33"),
    ):
        plan = calcular_plan(coste, vida, metodo, pct, date(2026, 10, 1))
        assert all(Decimal(f["acumulado"]) <= Decimal(coste) for f in plan), metodo
        assert plan[-1]["acumulado"] == coste


def test_plan_regresivo_decreciente_y_exacto() -> None:
    pct = "25.00"
    plan = calcular_plan("20000.0000", 48, "regresivo", pct, date(2026, 10, 1))
    cuotas = [Decimal(f["cuota"]) for f in plan]
    for k in range(1, len(cuotas)):
        assert cuotas[k] <= cuotas[k - 1]
    assert all(c > 0 for c in cuotas)
    assert plan[-1]["acumulado"] == "20000.0000"


def test_fracciones_prorrateo() -> None:
    assert fraccion_cuota_primera(date(2026, 1, 1), "mensual") == Decimal(1)
    assert fraccion_cuota_baja(date(2026, 3, 15), "mensual") == Decimal(1)
    # dias: 22 días restantes de enero (31) y 15/31 de marzo
    assert fraccion_cuota_primera(date(2026, 1, 10), "dias") == Decimal("0.7097")
    assert fraccion_cuota_baja(date(2026, 3, 15), "dias") == Decimal("0.4839")
    assert cuota_parcial_baja(date(2026, 6, 15), Decimal("250.0000"), "dias") == Decimal("125.0000")


def test_plan_lineal_dias_prorrateo_inicial() -> None:
    plan = calcular_plan("15000.0000", 60, "lineal", None, date(2026, 1, 10), prorrateo="dias")
    assert len(plan) == 60
    assert Decimal(plan[0]["cuota"]) == Decimal("177.4250")
    assert plan[-1]["acumulado"] == "15000.0000"


def test_avanzar_periodo() -> None:
    assert avanzar_periodo(2026, 12) == (2027, 1)
    assert avanzar_periodo(2026, 1) == (2026, 2)
    assert avanzar_periodo(2025, 11, saltos=3) == (2026, 2)


def test_replanear_pendientes_lineal() -> None:
    cuotas = replanear_pendientes("13750.0000", "lineal", None, 43)
    assert len(cuotas) == 43
    assert sum(cuotas, Decimal(0)) == Decimal("13750.0000")


def test_replanear_pendientes_regresivo() -> None:
    cuotas = replanear_pendientes("5000.0000", "regresivo", "25.00", 10)
    assert sum(cuotas, Decimal(0)) == Decimal("5000.0000")
    assert all(c > 0 for c in cuotas)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"coste": "15000.0000", "vida_util": 0, "metodo": "lineal", "porcentaje": None, "fecha_alta": date(2026, 1, 1)},
        {"coste": "0", "vida_util": 60, "metodo": "lineal", "porcentaje": None, "fecha_alta": date(2026, 1, 1)},
        {"coste": "-1.0000", "vida_util": 60, "metodo": "lineal", "porcentaje": None, "fecha_alta": date(2026, 1, 1)},
        {"coste": "15000.0000", "vida_util": 60, "metodo": "regresivo", "porcentaje": None, "fecha_alta": date(2026, 1, 1)},
        {"coste": "15000.0000", "vida_util": 60, "metodo": "regresivo", "porcentaje": "100.00", "fecha_alta": date(2026, 1, 1)},
        {"coste": "15000.0000", "vida_util": 60, "metodo": "regresivo", "porcentaje": "0.00", "fecha_alta": date(2026, 1, 1)},
        {"coste": "15000.0000", "vida_util": 60, "metodo": "decimal", "porcentaje": None, "fecha_alta": date(2026, 1, 1)},
    ],
)
def test_plan_rechaza_invalidos(kwargs: dict) -> None:
    with pytest.raises(InmovilizadoError):
        calcular_plan(**kwargs)