"""Saldo acumulado de la proyision (T014, US1/SC-002).

`saldo_k = saldo_inicial + S(movimientos de los buckets anteriores y del
propio)`, con precision `Decimal` exacta a 4 decimales (SC-005). El saldo final
de la cabecera es el acumulado del ultimo bucket, de modo que la serie nunca
se desalinea con la cabecera.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.cashflow.proyeccion import generar_prevision
from services.cashflow.saldos import saldo_tesoreria_inicial
from services.cashflow.utils import c4, fmt, suma_decimal
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026
DESDE = date(EJERCICIO, 9, 16)
HASTA = date(EJERCICIO, 9, 21)


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


# --- Aritmetica pura ---------------------------------------------------------


def test_suma_decimal_ignora_none_y_cuantiza():
    assert suma_decimal([]) == Decimal("0.0000")
    assert suma_decimal([None, Decimal("1.5"), "2.25"]) == Decimal("3.7500")


def test_c4_redondea_a_comercial():
    assert c4(Decimal("1.00005")) == Decimal("1.0001")
    assert c4(Decimal("1.00004")) == Decimal("1.0000")
    assert fmt(Decimal(2)) == "2.0000"
    assert fmt(None) == "0.0000"


# --- Saldo acumulado sobre la prevision -------------------------------------


async def _prevision_con_flujos(db, saldo_esperado_inicial: str = "0.0000"):
    """Manual: 500 de cobro el dia 16, 1200 de pago el 18, 300 de cobro el 21."""
    return await generar_prevision(
        db,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {
                "tipo": "cobro",
                "importe": "500.0000",
                "fecha_prevista": date(2026, 9, 16),
                "concepto": "Cobro previsto",
            },
            {
                "tipo": "pago",
                "importe": "1200.0000",
                "fecha_prevista": date(2026, 9, 18),
                "concepto": "Pago previsto",
            },
            {
                "tipo": "cobro",
                "importe": "300.0000",
                "fecha_prevista": date(2026, 9, 21),
                "concepto": "Cobro posterior",
            },
        ],
    )


async def test_saldo_acumulado_por_bucket(db_session):
    resultado = await _prevision_con_flujos(db_session)
    buckets = resultado["buckets"]
    assert [b["fecha"] for b in buckets] == [
        date(2026, 9, 16),
        date(2026, 9, 17),
        date(2026, 9, 18),
        date(2026, 9, 19),
        date(2026, 9, 20),
        date(2026, 9, 21),
    ]
    acumulados = [b["saldo_acumulado"] for b in buckets]
    assert acumulados == [
        Decimal("500.0000"),
        Decimal("500.0000"),
        Decimal("-700.0000"),
        Decimal("-700.0000"),
        Decimal("-700.0000"),
        Decimal("-400.0000"),
    ]
    assert resultado["prevision"].saldo_final == Decimal("-400.0000")


async def test_suma_de_movimientos_iguala_el_saldo_final(db_session):
    """SC-002: `saldo_inicial + S(movimientos) == saldo_final` exacto."""
    resultado = await _prevision_con_flujos(db_session)
    prevision = resultado["prevision"]
    variacion = suma_decimal(b["neto"] for b in resultado["buckets"])
    assert prevision.saldo_final == c4(prevision.saldo_inicial + variacion)
    assert variacion == Decimal("-400.0000")


async def test_saldo_inicial_toma_el_saldo_real_de_tesoreria(db_session):
    """research D1: sin conciliacion, el saldo inicial sale del diario (grupo 5)."""
    await soporte.plantar_cuenta(
        db_session, empresa_id=EMPRESA, code="1000", parent="100", name="Capital social"
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 1, 5),
        lineas=[
            {"cuenta": "5720", "debe": "5000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "5000.0000"},
        ],
        concepto="Aportacion de capital",
        tipo="OPENING",
    )
    await db_session.commit()
    saldo, origen = await saldo_tesoreria_inicial(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE
    )
    assert saldo == Decimal("5000.0000")
    assert origen == "diario"

    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=date(EJERCICIO, 9, 17),
        granularidad="dia",
        movimientos_manuales=[
            {
                "tipo": "pago",
                "importe": "1000.0000",
                "fecha_prevista": date(2026, 9, 16),
            }
        ],
    )
    assert resultado["prevision"].saldo_inicial == Decimal("5000.0000")
    assert resultado["prevision"].origen_saldo_inicial == "diario"
    assert resultado["prevision"].saldo_final == Decimal("4000.0000")


async def test_saldo_inicial_usa_la_conciliacion_si_existe(db_session):
    """research D1/FR-005: la conciliacion bancaria tiene precedencia."""
    from models.treasury.conciliacion import Conciliacion, ConciliacionEstado

    await soporte.plantar_cuenta(
        db_session, empresa_id=EMPRESA, code="1000", parent="100", name="Capital social"
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 1, 5),
        lineas=[
            {"cuenta": "5720", "debe": "1000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "1000.0000"},
        ],
        tipo="OPENING",
    )
    cuentas = await soporte.cuentas(db_session, EMPRESA)
    db_session.add(
        Conciliacion(
            empresa_id=EMPRESA,
            cuenta_id=cuentas["5720"],
            ejercicio=EJERCICIO,
            fecha_inicio=date(EJERCICIO, 1, 1),
            fecha_fin=date(EJERCICIO, 3, 31),
            saldo_banco=Decimal("1234.0000"),
            saldo_libros=Decimal("1000.0000"),
            diferencia=Decimal("234.0000"),
            estado=ConciliacionEstado.cerrada,
        )
    )
    await db_session.commit()

    saldo, origen = await saldo_tesoreria_inicial(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE
    )
    assert saldo == Decimal("1234.0000")
    assert origen == "conciliacion"


async def test_saldo_inicial_ignora_las_cuentas_no_tesoreria(db_session):
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 5, 1),
        lineas=[
            {"cuenta": "4300", "debe": "9000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "9000.0000"},
        ],
        concepto="Factura de venta (no es tesoreria)",
    )
    await db_session.commit()

    saldo, origen = await saldo_tesoreria_inicial(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE
    )
    assert saldo == Decimal("0.0000")
    assert origen == "diario"


async def test_cifras_con_cuatro_decimales_no_pierden_precision(db_session):
    """SC-005: el saldo acumulado conserva los 4 decimales del sector."""
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=date(EJERCICIO, 9, 17),
        granularidad="dia",
        movimientos_manuales=[
            {
                "tipo": "cobro",
                "importe": "0.1000",
                "fecha_prevista": date(2026, 9, 16),
            },
            {
                "tipo": "pago",
                "importe": "0.2000",
                "fecha_prevista": date(2026, 9, 17),
            },
        ],
    )
    acumulados = [b["saldo_acumulado"] for b in resultado["buckets"]]
    assert acumulados == [Decimal("0.1000"), Decimal("-0.1000")]
    assert resultado["prevision"].saldo_final == Decimal("-0.1000")
