"""Proyeccion de vencimientos y agrupacion por granularidad (T012, US1/SC-001).

Verifica que los vencimientos pendientes de SPEC-011/020 se colocan en la fecha
de vencimiento y que la agregacion dia/semana/mes es la que fija research.md D2
(dia = la fecha, semana = el lunes ISO, mes = el dia 1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.treasury.movimiento_prevision import MovimientoPrevision
from services.cashflow.proyeccion import (
    recuperar_movimientos_proyectables,
)
from services.cashflow.utils import (
    agrupar_en_buckets,
    clave_bucket,
    enumerar_buckets,
)
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026
DESDE = date(EJERCICIO, 9, 16)
HASTA = date(EJERCICIO, 12, 31)


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


# --- Buckets puros (research D2) --------------------------------------------


def test_clave_bucket_dia():
    assert clave_bucket(date(2026, 9, 16), "dia") == date(2026, 9, 16)
    assert clave_bucket(date(2026, 9, 20), "dia") == date(2026, 9, 20)


def test_clave_bucket_semana_usa_el_lunes():
    # 2026-09-16 es miércoles -> su lunes es 2026-09-14.
    assert clave_bucket(date(2026, 9, 16), "semana") == date(2026, 9, 14)
    # 2026-09-20 es domingo -> cierra la semana que empezó el 14.
    assert clave_bucket(date(2026, 9, 20), "semana") == date(2026, 9, 14)
    assert clave_bucket(date(2026, 9, 21), "semana") == date(2026, 9, 21)
    assert clave_bucket(date(2026, 9, 14), "semana") == date(2026, 9, 14)


def test_clave_bucket_mes_usa_el_dia_uno():
    assert clave_bucket(date(2026, 9, 16), "mes") == date(2026, 9, 1)
    assert clave_bucket(date(2026, 12, 31), "mes") == date(2026, 12, 1)


def test_granularidad_desconocida_rechazada():
    with pytest.raises(ValueError):
        clave_bucket(date(2026, 9, 16), "trimestre")


def test_enumerar_buckets_sin_huecos():
    dias = enumerar_buckets(DESDE, date(2026, 9, 19), "dia")
    assert dias == [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 19)]
    semanas = enumerar_buckets(DESDE, date(2026, 10, 15), "semana")
    assert semanas == [
        date(2026, 9, 14),
        date(2026, 9, 21),
        date(2026, 9, 28),
        date(2026, 10, 5),
        date(2026, 10, 12),
    ]
    meses = enumerar_buckets(DESDE, date(2026, 12, 31), "mes")
    assert meses == [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)]


def test_agrupar_suma_cobros_y_pagos_por_bucket():
    movimientos = [
        {"fecha_prevista": date(2026, 9, 16), "tipo": "cobro", "importe": Decimal("100.0000")},
        {"fecha_prevista": date(2026, 9, 17), "tipo": "cobro", "importe": Decimal("50.0000")},
        {"fecha_prevista": date(2026, 9, 18), "tipo": "pago", "importe": Decimal("30.0000")},
        {"fecha_prevista": date(2026, 9, 21), "tipo": "pago", "importe": Decimal("10.0000")},
    ]
    por_dia = agrupar_en_buckets(movimientos, "dia")
    assert [b.fecha for b in por_dia] == [
        date(2026, 9, 16),
        date(2026, 9, 17),
        date(2026, 9, 18),
        date(2026, 9, 21),
    ]
    assert por_dia[0].cobros == Decimal("100.0000")
    assert por_dia[0].neto == Decimal("100.0000")
    assert por_dia[2].pagos == Decimal("30.0000")
    assert por_dia[2].neto == Decimal("-30.0000")

    # Las cuatro caen en semanas ISO distintas (16 y 17 en la del 14; 18 en la
    # misma; 21 abre la siguiente).
    por_semana = agrupar_en_buckets(movimientos, "semana")
    assert [b.fecha for b in por_semana] == [date(2026, 9, 14), date(2026, 9, 21)]
    assert por_semana[0].cobros == Decimal("150.0000")
    assert por_semana[0].pagos == Decimal("30.0000")
    assert por_semana[0].neto == Decimal("120.0000")
    assert por_semana[1].pagos == Decimal("10.0000")
    assert por_semana[1].neto == Decimal("-10.0000")


def test_agrupar_ignora_movimientos_sin_fecha():
    movimientos = [
        {"fecha_prevista": None, "tipo": "pago", "importe": Decimal("99.0000")},
        {"fecha_prevista": date(2026, 9, 16), "tipo": "cobro", "importe": Decimal("10.0000")},
    ]
    por_dia = agrupar_en_buckets(movimientos, "dia")
    assert len(por_dia) == 1
    assert por_dia[0].cobros == Decimal("10.0000")


# --- Vencimientos proyectables (SPEC-011/020) -------------------------------


async def test_vencimiento_pendiente_se_proyecta_en_su_fecha(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 30),
        importe="1500.0000",
        recibo_num="R-30",
    )
    await db_session.commit()

    proyectados, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert excluidos == []
    assert len(proyectados) == 1
    assert proyectados[0]["fecha_prevista"] == date(2026, 9, 30)
    assert proyectados[0]["importe"] == Decimal("1500.0000")
    assert proyectados[0]["tipo"] == "cobro"


async def test_vencimiento_de_cobro_y_de_pago_se_clasifican(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 10, 15),
        importe="800.0000",
        tipo="pago",
        recibo_num="R-15",
    )
    await db_session.commit()

    proyectados, _ = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert proyectados[0]["tipo"] == "pago"


async def test_saldo_parcial_proyecta_solo_el_saldo_pendiente(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 30),
        importe="1000.0000",
        acumulado="250.0000",
        recibo_num="R-PARCIAL",
    )
    await db_session.commit()

    proyectados, _ = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert proyectados[0]["importe"] == Decimal("750.0000")


async def test_todos_los_vencimientos_pendientes_entran(db_session):
    """SC-001: el 100 % de los pendientes se proyecta en su fecha."""
    fechas = [date(2026, 9, 30), date(2026, 10, 15), date(2026, 11, 3), date(2026, 12, 1)]
    for indice, fecha in enumerate(fechas, start=1):
        await soporte.vencimiento(
            db_session,
            empresa_id=EMPRESA,
            fecha_vencimiento=fecha,
            importe=f"{indice * 100}.0000",
            recibo_num=f"R-{indice:03d}",
        )
    await db_session.commit()

    proyectados, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert excluidos == []
    assert sorted(p["fecha_prevista"] for p in proyectados) == fechas
    movimientos = (
        await db_session.scalars(select(MovimientoPrevision))
    ).all()
    assert movimientos == []
