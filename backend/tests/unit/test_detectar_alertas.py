"""Deteccion de saldo negativo por bucket (T031, US3/FR-003/SC-004).

research.md D6: al generar la prevision se crea una alerta por cada bucket con
`saldo_acumulado < 0`. SC-004 exige el 100 % de los periodos negativos, y el
saldo es **acumulado**: una racha de deficit produce una alerta por periodo
(hasta que un cobro lo cubre), no una sola alerta por racha.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.cashflow.alertas import detectar_alertas, listar_alertas
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


async def _prevision(db, manual: dict[str, object]):
    return await generar_prevision(
        db,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[manual],
    )


PAGO_1000 = {"tipo": "pago", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 16)}


# --- Deteccion (FR-003) ------------------------------------------------------


async def test_saldo_negativo_genera_alerta(db_session):
    resultado = await _prevision(db_session, PAGO_1000)
    # El pago del dia 16 deja el saldo en -1000 los tres dias del rango.
    assert len(resultado["alertas"]) == 3
    alerta = resultado["alertas"][0]
    assert alerta.saldo_proyectado == Decimal("-1000.0000")
    assert alerta.importe_deficit == Decimal("1000.0000")
    assert alerta.estado.value == "abierta"
    assert alerta.fecha == date(2026, 9, 16)


async def test_alerta_apunta_al_pago_del_bucket(db_session):
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=date(2026, 9, 16),
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "pago", "importe": "300.0000", "fecha_prevista": date(2026, 9, 16)},
            {"tipo": "pago", "importe": "900.0000", "fecha_prevista": date(2026, 9, 16)},
        ],
    )
    alerta = resultado["alertas"][0]
    assert alerta.accion_sugerida.value == "reprogramar_pago"
    from models.treasury.movimiento_prevision import MovimientoPrevision

    movimiento = await db_session.get(MovimientoPrevision, alerta.movimiento_origen_id)
    assert movimiento is not None
    # El candidato es el pago mas alto del bucket negativo.
    assert movimiento.importe == Decimal("900.0000")
    assert movimiento.tipo.value == "pago"


async def test_bucket_sin_pago_propio_sugiere_incluir_ingreso(db_session):
    """Tras el dia del pago no queda nada que reprogramar: se propone un ingreso."""
    resultado = await _prevision(db_session, PAGO_1000)
    acciones = [a.accion_sugerida.value for a in resultado["alertas"]]
    assert acciones == ["reprogramar_pago", "incluir_ingreso", "incluir_ingreso"]
    # Solo la primera alerta apunta a un movimiento.
    assert resultado["alertas"][0].movimiento_origen_id is not None
    assert resultado["alertas"][1].movimiento_origen_id is None


async def test_el_deficit_de_una_racha_es_el_mismo(db_session):
    """Sin movimientos nuevos, `importe_deficit` no se infla periodo a periodo."""
    resultado = await _prevision(db_session, PAGO_1000)
    assert {a.importe_deficit for a in resultado["alertas"]} == {Decimal("1000.0000")}


async def test_un_cobro_que_cubre_el_deficit_cierra_la_alerta(db_session):
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "pago", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 16)},
            {"tipo": "cobro", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 18)},
        ],
    )
    # 16 y 17 negativos, 18 vuelve a cero (limite de solvencia, sin alerta).
    assert [a.fecha for a in resultado["alertas"]] == [date(2026, 9, 16), date(2026, 9, 17)]
    assert resultado["prevision"].saldo_final == Decimal("0.0000")


async def test_saldo_inicial_positivo_evita_la_alerta(db_session):
    """Con tesoreria de partida el mismo pago no genera deficit."""
    await soporte.plantar_cuenta(
        db_session, empresa_id=EMPRESA, code="1000", parent="100", name="Capital"
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 1, 2),
        lineas=[
            {"cuenta": "5720", "debe": "5000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "5000.0000"},
        ],
        tipo="OPENING",
    )
    await db_session.commit()

    resultado = await _prevision(db_session, PAGO_1000)
    assert resultado["alertas"] == []
    assert resultado["prevision"].saldo_final == Decimal("4000.0000")


async def test_alertas_se_persisten_con_la_prevision(db_session):
    resultado = await _prevision(db_session, PAGO_1000)
    await db_session.commit()

    listado = await listar_alertas(
        db_session, empresa_id=EMPRESA, prevision_id=resultado["id"]
    )
    assert listado["total"] == 3
    assert listado["items"][0].id == resultado["alertas"][0].id
    assert [a.estado.value for a in listado["items"]] == ["abierta"] * 3


async def test_una_alerta_por_bucket(db_session):
    """El indice unico (empresa, prevision, fecha) evita duplicar en el mismo dia."""
    from sqlalchemy import func, select

    from models.treasury.alerta_liquidez import AlertaLiquidez

    resultado = await _prevision(db_session, PAGO_1000)
    await db_session.commit()
    fechas = (
        await db_session.scalars(
            select(AlertaLiquidez.fecha).where(
                AlertaLiquidez.prevision_id == resultado["id"]
            )
        )
    ).all()
    assert len(fechas) == len(set(fechas))
    count = await db_session.scalar(
        select(func.count()).select_from(AlertaLiquidez).where(
            AlertaLiquidez.prevision_id == resultado["id"]
        )
    )
    assert count == 3


async def test_detectar_alertas_sobre_buckets_externos(db_session):
    """`detectar_alertas` tambien se puede lanzar sobre buckets calculados."""
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

    buckets = [
        {
            "fecha": date(2026, 9, 16),
            "saldo_acumulado": Decimal("100.0000"),
            "cobros": Decimal("100.0000"),
            "pagos": Decimal(0),
        },
        {
            "fecha": date(2026, 9, 17),
            "saldo_acumulado": Decimal("-250.0000"),
            "cobros": Decimal(0),
            "pagos": Decimal("350.0000"),
        },
    ]
    creadas = await detectar_alertas(
        db_session, empresa_id=EMPRESA, prevision=prevision, buckets=buckets
    )
    assert len(creadas) == 1
    assert creadas[0].importe_deficit == Decimal("250.0000")
    assert creadas[0].accion_sugerida.value == "incluir_ingreso"


async def test_alerta_por_deficit_con_cuatro_decimales(db_session):
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=date(2026, 9, 16),
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "pago", "importe": "0.1000", "fecha_prevista": date(2026, 9, 16)}
        ],
    )
    assert resultado["alertas"][0].saldo_proyectado == Decimal("-0.1000")
    assert resultado["alertas"][0].importe_deficit == Decimal("0.1000")
