"""SPEC-026 US2 · T019: desviacion absoluta `real - presupuesto` (research.md D2).

Cubre el quickstart (real 45000 vs presupuesto 48000 -> -3000.0000; real 50000
vs 48000 -> 2000.0000), la convencion de signos por grupo (6 suma Debe, 7 suma
Haber) y la precision exacta de 4 decimales (SC-002/SC-005).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.budget.desviaciones import calcular_desviaciones
from services.budget.utils import (
    calcular_desviacion_absoluta,
    calcular_desviacion_relativa,
    calcular_real,
)
from tests.unit.budget_support import (
    cuentas,
    empresa,
    presupuesto_directo,
    publicar_asiento,
)

EMPRESA = 10
EJERCICIO = 2026


# --- Convencion de signos D2 (funcion pura) -------------------------------


def test_grupo_6_usa_debe():
    assert calcular_real(6, Decimal(45000), Decimal(3000)) == Decimal("45000.0000")


def test_grupo_7_usa_haber():
    assert calcular_real(7, Decimal(3000), Decimal(120000)) == Decimal("120000.0000")


def test_resto_de_grupos_usa_neto():
    assert calcular_real(4, Decimal(900), Decimal(1200)) == Decimal("-300.0000")


def test_real_cuantiza_a_cuatro_decimales():
    assert calcular_real(6, Decimal("1.00005"), Decimal(0)) == Decimal("1.0001")


# --- Desviacion absoluta ---------------------------------------------------


def test_quickstart_45000_contra_48000():
    assert calcular_desviacion_absoluta(Decimal(45000), Decimal(48000)) == Decimal(
        "-3000.0000"
    )


def test_quickstart_50000_contra_48000():
    assert calcular_desviacion_absoluta(Decimal(50000), Decimal(48000)) == Decimal(
        "2000.0000"
    )


def test_desviacion_cero():
    assert calcular_desviacion_absoluta(Decimal(100), Decimal(100)) == Decimal(
        "0.0000"
    )


def test_desviacion_ingreso_usa_signo_positivo_de_haber():
    """Grupo 7: superar el ingreso presupuestado tambien es desviacion positiva."""
    real = calcular_real(7, Decimal(0), Decimal(130000))
    assert calcular_desviacion_absoluta(real, Decimal(120000)) == Decimal("10000.0000")


# --- Desviacion sobre el diario real ---------------------------------------


@pytest.fixture
async def base(db_session):
    await empresa(db_session, EMPRESA)
    return await cuentas(db_session, EMPRESA)


async def test_desviacion_de_un_gasto_real(db_session, base):
    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["6400"],
        importe="48000.0000",
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 6, 30),
        lineas=[
            {"account_id": base["6400"], "debit": "45000", "credit": "0"},
            {"account_id": base["4000"], "debit": "0", "credit": "45000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    fila = next(i for i in informe["items"] if i["codigo_cuenta"] == "6400")
    assert fila["importe_presupuestado"] == "48000.0000"
    assert fila["importe_real"] == "45000.0000"
    assert fila["desviacion_absoluta"] == "-3000.0000"
    assert fila["sin_presupuesto"] is False


async def test_desviacion_de_un_ingreso_real_usa_haber(db_session, base):
    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["7000"],
        importe="120000.0000",
        tipo="ingreso",
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 15),
        lineas=[
            {"account_id": base["4300"], "debit": "50000", "credit": "0"},
            {"account_id": base["7000"], "debit": "0", "credit": "50000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    fila = next(i for i in informe["items"] if i["codigo_cuenta"] == "7000")
    assert fila["importe_real"] == "50000.0000"
    assert fila["desviacion_absoluta"] == "-70000.0000"


async def test_todas_las_desviaciones_cuadran_con_resta_menos_presupuesto(
    db_session, base
):
    """SC-002: el 100 % de las desviaciones cuadran con real - presupuesto."""
    from decimal import Decimal as D

    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["6400"],
        importe="48000.0000",
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 2, 28),
        lineas=[
            {"account_id": base["6400"], "debit": "12345.6789", "credit": "0"},
            {"account_id": base["4000"], "debit": "0", "credit": "12345.6789"},
        ],
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 4, 30),
        lineas=[
            {"account_id": base["6000"], "debit": "777.7777", "credit": "0"},
            {"account_id": base["4100"], "debit": "0", "credit": "777.7777"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["items"]
    for item in informe["items"]:
        esperado = D(item["importe_real"]) - D(item["importe_presupuestado"])
        assert D(item["desviacion_absoluta"]) == esperado
        assert len(item["desviacion_absoluta"].split(".")[1]) == 4


def test_relativa_coincide_con_la_formula():
    real, presupuesto = Decimal(45000), Decimal(48000)
    esperado = (real - presupuesto) / abs(presupuesto)
    assert calcular_desviacion_relativa(real, presupuesto) == esperado.quantize(
        Decimal("0.0001")
    )
