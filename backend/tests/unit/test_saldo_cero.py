"""Saldo exactamente cero: limite de solvencia sin alerta (T032, edge case del spec).

"El saldo proyectado es exactamente cero -> se muestra como limite de solvencia,
sin alerta negativa." El saldo cero NO puede disparar una alerta porque la
columna exige `saldo_proyectado < 0` (constraint del modelo, no solo del servicio).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.treasury.alerta_liquidez import AlertaLiquidez
from services.cashflow.alertas import listar_alertas
from services.cashflow.proyeccion import generar_prevision
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026
DESDE = date(EJERCICIO, 9, 16)
HASTA = date(EJERCICIO, 9, 18)


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


async def test_saldo_cero_no_genera_alerta(db_session):
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "cobro", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 16)},
            {"tipo": "pago", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 17)},
        ],
    )
    assert resultado["alertas"] == []
    saldos = [b["saldo_acumulado"] for b in resultado["buckets"]]
    assert saldos == [
        Decimal("1000.0000"),
        Decimal("0.0000"),
        Decimal("0.0000"),
    ]
    assert resultado["prevision"].saldo_final == Decimal("0.0000")
    assert resultado["prevision"].saldo_final == Decimal(0)


async def test_saldo_cero_es_visible_en_la_serie(db_session):
    """El limite de solvencia se ve: el bucket existe, simplemente no alerta."""
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "cobro", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 16)},
            {"tipo": "pago", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 17)},
        ],
    )
    bucket_cero = next(
        b for b in resultado["buckets"] if b["saldo_acumulado"] == Decimal("0.0000")
    )
    assert bucket_cero["fecha"] == date(2026, 9, 17)
    assert bucket_cero["neto"] == Decimal("-1000.0000")


async def test_solo_el_saldo_negativo_alerta_no_el_cero(db_session):
    """El cobro deja 0, el pago lo lleva a -500: solo el segundo alerta."""
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "cobro", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 16)},
            {"tipo": "pago", "importe": "1500.0000", "fecha_prevista": date(2026, 9, 17)},
        ],
    )
    alertas = resultado["alertas"]
    assert [a.fecha for a in alertas] == [date(2026, 9, 17), date(2026, 9, 18)]
    assert all(a.saldo_proyectado < 0 for a in alertas)
    assert all(a.importe_deficit == -a.saldo_proyectado for a in alertas)


async def test_el_modelo_rechaza_una_alerta_en_saldo_cero(db_session):
    """La garantia es del modelo, no del servicio: `saldo_proyectado < 0`."""
    from models.treasury.prevision import (
        EstadoPrevision,
        GranularidadPrevision,
        PrevisionTesoreria,
    )

    prevision = PrevisionTesoreria(
        empresa_id=EMPRESA,
        numero_prevision=1,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad=GranularidadPrevision.dia,
        estado=EstadoPrevision.generada,
    )
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(
        AlertaLiquidez(
            empresa_id=EMPRESA,
            prevision_id=prevision.id,
            fecha=date(2026, 9, 17),
            saldo_proyectado=Decimal("0.0000"),
            importe_deficit=Decimal("0.0000"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_saldo_positivo_no_alerta_tampoco(db_session):
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "cobro", "importe": "5000.0000", "fecha_prevista": date(2026, 9, 16)}
        ],
    )
    assert resultado["alertas"] == []
    await db_session.commit()
    listado = await listar_alertas(db_session, empresa_id=EMPRESA, prevision_id=resultado["id"])
    assert listado["total"] == 0
    assert (
        await db_session.scalars(
            select(AlertaLiquidez).where(AlertaLiquidez.empresa_id == EMPRESA)
        )
    ).all() == []
