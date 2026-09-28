"""SPEC-026 US2 · T020: desviacion relativa `NUMERIC(7,4)` (research.md D2/D4).

Con presupuesto distinto de cero se calcula `(real - presupuesto) /
|presupuesto|`; con presupuesto cero la relativa es `None` (dividir entre cero
no tiene sentido financiero). Verifica tambien la precision de 4 decimales del
ratio (SC-005) y su rango `NUMERIC(7,4)`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.budget.desviaciones import calcular_desviaciones
from services.budget.utils import RATIO_MAXIMO, c4_ratio, calcular_desviacion_relativa
from tests.unit.budget_support import (
    cuentas,
    empresa,
    presupuesto_directo,
    publicar_asiento,
)

EMPRESA = 10
EJERCICIO = 2026


def _ratio(real: str, presupuesto: str) -> Decimal:
    return calcular_desviacion_relativa(Decimal(real), Decimal(presupuesto))


def test_relativa_por_debajo_del_presupuesto():
    assert _ratio("45000", "48000") == Decimal("-0.0625")


def test_relativa_por_encima_del_presupuesto():
    assert _ratio("50000", "48000") == Decimal("0.0417")


def test_relativa_con_presupuesto_negativo_usa_valor_absoluto():
    """`(real - presupuesto) / |presupuesto|`: con presupuesto -120000 y real
    130000 la desviacion es 250000 y el ratio 2.0833 (no -2.0833)."""
    assert _ratio("130000", "-120000") == Decimal("2.0833")
    assert _ratio("130000", "120000") == Decimal("0.0833")


def test_relativa_con_presupuesto_cero_es_none():
    assert _ratio("2000", "0") is None


def test_relativa_exacta_al_ajustar_a_cuatro_decimales():
    assert _ratio("1000", "3") == Decimal("332.3333")


def test_ratio_se_satura_al_rango_de_numeric_7_4():
    """Un ratio mayor que 999.9999 saturaria la columna; se acota."""
    assert c4_ratio(Decimal(100000)) == RATIO_MAXIMO
    assert c4_ratio(Decimal(-100000)) == Decimal("-999.9999")
    assert _ratio("1000000", "1") == RATIO_MAXIMO


def test_ratio_normal_no_se_satura():
    assert c4_ratio(Decimal("0.0625")) == Decimal("0.0625")


@pytest.fixture
async def base(db_session):
    await empresa(db_session, EMPRESA)
    return await cuentas(db_session, EMPRESA)


async def test_relativa_en_la_api_de_seguimiento(db_session, base):
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
        fecha=date(EJERCICIO, 5, 31),
        lineas=[
            {"account_id": base["6400"], "debit": "45000", "credit": "0"},
            {"account_id": base["4000"], "debit": "0", "credit": "45000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, cuenta_id=base["6400"]
    )
    assert informe["total"] == 1
    assert informe["items"][0]["desviacion_relativa"] == "-0.0625"
    assert len(informe["items"][0]["desviacion_relativa"].split(".")[1]) == 4


async def test_relativa_null_sin_presupuesto(db_session, base):
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 7, 31),
        lineas=[
            {"account_id": base["6400"], "debit": "2000", "credit": "0"},
            {"account_id": base["4000"], "debit": "0", "credit": "2000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, cuenta_id=base["6400"]
    )
    fila = informe["items"][0]
    assert fila["sin_presupuesto"] is True
    assert fila["importe_presupuestado"] == "0.0000"
    assert fila["desviacion_relativa"] is None
