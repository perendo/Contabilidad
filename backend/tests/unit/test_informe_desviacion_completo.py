"""SPEC-026 US3 · T028: el informe lista todas las cuentas y centros (FR-003).

El informe acumulado debe incluir tanto las combinaciones con presupuesto como
las marcadas `sin_presupuesto`, y sus totales deben ser exactamente la suma de
las lineas (`total_presupuestado`, `total_real` y `total_desviacion`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.budget.informe_desviacion import generar_informe_desviacion
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


async def _escenario(db, plan, con_centro: bool = True):
    centro = await crear_centro(db, EMPRESA) if con_centro else None
    await presupuesto_directo(
        db,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["6400"],
        importe="48000.0000",
        centro_coste_id=centro,
    )
    await presupuesto_directo(
        db,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["7000"],
        importe="120000.0000",
        tipo="ingreso",
    )
    await publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 6, 30),
        lineas=[
            {
                "account_id": plan["6400"],
                "debit": "50000",
                "credit": "0",
                "centro_coste_id": str(centro) if centro else None,
            },
            {"account_id": plan["4000"], "debit": "0", "credit": "50000"},
        ],
    )
    await publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 6, 30),
        lineas=[
            {"account_id": plan["4300"], "debit": "130000", "credit": "0"},
            {"account_id": plan["7000"], "debit": "0", "credit": "130000"},
        ],
    )
    await publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 7, 15),
        lineas=[
            {"account_id": plan["6000"], "debit": "3333.3333", "credit": "0"},
            {"account_id": plan["4100"], "debit": "0", "credit": "3333.3333"},
        ],
    )
    await db.commit()
    return centro


async def test_informe_incluye_sin_presupuesto_y_totales_cuadran(db_session, base):
    await _escenario(db_session, base)

    informe = await generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
    )
    assert informe["origen"] == "calculo"
    assert informe["lineas_sin_presupuesto"] >= 1
    assert any(i["sin_presupuesto"] for i in informe["items"])
    assert any(not i["sin_presupuesto"] for i in informe["items"])

    suma_presupuesto = sum(
        (Decimal(i["importe_presupuestado"]) for i in informe["items"]), Decimal(0)
    )
    suma_real = sum((Decimal(i["importe_real"]) for i in informe["items"]), Decimal(0))
    suma_desviacion = sum(
        (Decimal(i["desviacion_absoluta"]) for i in informe["items"]), Decimal(0)
    )
    assert Decimal(informe["total_presupuestado"]) == suma_presupuesto
    assert Decimal(informe["total_real"]) == suma_real
    assert Decimal(informe["total_desviacion"]) == suma_desviacion
    assert informe["cuadra"] is True
    assert informe["total"] == len(informe["items"])


async def test_informe_agrupa_por_centro(db_session, base):
    centro = await _escenario(db_session, base)

    informe = await generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
    )
    por_codigo = {c["nombre_centro"]: c for c in informe["centros"]}
    assert "Sin centro" in por_codigo
    con_centro = [c for c in informe["centros"] if c["centro_coste_id"] == str(centro)]
    assert len(con_centro) == 1
    assert con_centro[0]["importe_presupuestado"] == "48000.0000"
    assert con_centro[0]["importe_real"] == "50000.0000"
    assert con_centro[0]["desviacion_absoluta"] == "2000.0000"

    total_subtotales = sum(
        (Decimal(c["importe_real"]) for c in informe["centros"]), Decimal(0)
    )
    assert total_subtotales == Decimal(informe["total_real"])


async def test_informe_filtrado_por_mes(db_session, base):
    await _escenario(db_session, base)

    julio = await generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, mes=7
    )
    assert julio["mes"] == 7
    fila_6000 = next(i for i in julio["items"] if i["codigo_cuenta"] == "6000")
    assert fila_6000["importe_real"] == "3333.3333"

    junio = await generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, mes=6
    )
    # En junio la 6000 no tiene movimiento: sin presupuesto y sin real no
    # aparece en el informe (solo se listan combinaciones con datos, D4).
    assert not [i for i in junio["items"] if i["codigo_cuenta"] == "6000"]


async def test_informe_paginado(db_session, base):
    await _escenario(db_session, base)

    pagina = await generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, page=1, page_size=2
    )
    assert len(pagina["items"]) == 2
    assert pagina["total"] > 2

    siguiente = await generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, page=2, page_size=2
    )
    assert pagina["items"][0]["codigo_cuenta"] != siguiente["items"][0]["codigo_cuenta"]


async def test_informe_sin_datos_devuelve_totales_a_cero(db_session, base):
    informe = await generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=2027
    )
    assert informe["total_presupuestado"] == "0.0000"
    assert informe["total_real"] == "0.0000"
    assert informe["total_desviacion"] == "0.0000"
    assert informe["items"] == []
    assert informe["cuadra"] is True
