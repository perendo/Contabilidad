"""SPEC-026 US2 · T021: cuentas sin presupuesto (research.md D4, FR-006).

Una cuenta con real distinto de cero y sin linea de presupuesto aparece en el
seguimiento con `sin_presupuesto = true`, presupuesto 0 y desviacion igual al
real. Tambien cubre cuentas sin centro de coste (FR-006): el seguimiento se
hace solo por cuenta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.budget.desviaciones import calcular_desviaciones
from tests.unit.budget_support import (
    crear_centro,
    cuentas,
    empresa,
    presupuesto_directo,
    publicar_asiento,
)

EMPRESA = 10
EJERCICIO = 2026


@pytest.fixture
async def base(db_session):
    await empresa(db_session, EMPRESA)
    return await cuentas(db_session, EMPRESA)


async def test_cuenta_sin_presupuesto_aparece_con_el_real(db_session, base):
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 9, 30),
        lineas=[
            {"account_id": base["6000"], "debit": "2000", "credit": "0"},
            {"account_id": base["4100"], "debit": "0", "credit": "2000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    fila = next(i for i in informe["items"] if i["codigo_cuenta"] == "6000")
    assert fila["sin_presupuesto"] is True
    assert fila["importe_presupuestado"] == "0.0000"
    assert fila["importe_real"] == "2000.0000"
    assert fila["desviacion_absoluta"] == "2000.0000"
    assert fila["desviacion_relativa"] is None
    assert fila["centro_coste_id"] is None
    assert fila["nombre_centro"] is None


async def test_cuenta_con_y_sin_presupuesto_conviven(db_session, base):
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
        fecha=date(EJERCICIO, 9, 30),
        lineas=[
            {"account_id": base["6400"], "debit": "10000", "credit": "0"},
            {"account_id": base["4100"], "debit": "0", "credit": "10000"},
        ],
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 9, 30),
        lineas=[
            {"account_id": base["6000"], "debit": "3000", "credit": "0"},
            {"account_id": base["4100"], "debit": "0", "credit": "3000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    con = [i for i in informe["items"] if not i["sin_presupuesto"]]
    sin = [i for i in informe["items"] if i["sin_presupuesto"]]
    assert [i["codigo_cuenta"] for i in con] == ["6400"]
    assert "6000" in {i["codigo_cuenta"] for i in sin}


async def test_presupuesto_sin_real_aparece_con_real_cero(db_session, base):
    """Edge case del spec: sin datos reales, desviacion = -presupuesto."""
    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["6400"],
        importe="48000.0000",
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["total"] == 1
    fila = informe["items"][0]
    assert fila["importe_real"] == "0.0000"
    assert fila["desviacion_absoluta"] == "-48000.0000"
    assert fila["desviacion_relativa"] == "-1.0000"
    assert fila["sin_presupuesto"] is False


async def test_fr006_seguimiento_por_cuenta_sin_centro(db_session, base):
    """Cuenta presupuestada sin centro: la desviacion se calcula solo por cuenta."""
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
        fecha=date(EJERCICIO, 8, 31),
        lineas=[
            {"account_id": base["6400"], "debit": "50000", "credit": "0"},
            {"account_id": base["4000"], "debit": "0", "credit": "50000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    fila = next(i for i in informe["items"] if i["codigo_cuenta"] == "6400")
    assert fila["centro_coste_id"] is None
    assert fila["desviacion_absoluta"] == "2000.0000"
    assert Decimal(fila["desviacion_absoluta"]) == Decimal(50000) - Decimal(48000)


async def test_seguimiento_por_centro_con_imputacion(db_session, base):
    """La dimension de centro se toma de `journal_entry_line.centro_coste_id`."""
    centro = await crear_centro(db_session, EMPRESA)
    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["6400"],
        importe="48000.0000",
        centro_coste_id=centro,
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 8, 31),
        lineas=[
            {
                "account_id": base["6400"],
                "debit": "50000",
                "credit": "0",
                "centro_coste_id": str(centro),
            },
            {"account_id": base["4000"], "debit": "0", "credit": "50000"},
        ],
    )
    await db_session.commit()

    informe = await calcular_desviaciones(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    fila = next(i for i in informe["items"] if i["codigo_cuenta"] == "6400")
    assert fila["centro_coste_id"] == str(centro)
    assert fila["nombre_centro"] is not None
    assert "CC-01" in fila["nombre_centro"]
    assert fila["desviacion_absoluta"] == "2000.0000"


async def test_real_fuera_del_rango_no_cuenta(db_session, base):
    """El filtro por mes ignora los asientos de otros periodos (D3)."""
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
        fecha=date(EJERCICIO, 2, 10),
        lineas=[
            {"account_id": base["6400"], "debit": "1000", "credit": "0"},
            {"account_id": base["4000"], "debit": "0", "credit": "1000"},
        ],
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 11, 10),
        lineas=[
            {"account_id": base["6400"], "debit": "7000", "credit": "0"},
            {"account_id": base["4000"], "debit": "0", "credit": "7000"},
        ],
    )
    await db_session.commit()

    febrero = await calcular_desviaciones(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, mes=2
    )
    fila = next(i for i in febrero["items"] if i["codigo_cuenta"] == "6400")
    assert fila["importe_real"] == "1000.0000"
    assert febrero["desde"] == "2026-02-01"
    assert febrero["hasta"] == "2026-02-28"
