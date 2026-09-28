"""Exclusion de vencidos y cobrados de la proyeccion (T013, US1/FR-006).

Cubre el edge case del spec: "los vencidos y cobrados se excluyen", y que todo
excluido se reporta con su motivo para que el usuario entienda el hueco.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.treasury.movimiento_prevision import MovimientoPrevision
from services.cashflow.errores import CashflowError
from services.cashflow.proyeccion import (
    MOTIVO_ANULADO,
    MOTIVO_COBRADO,
    MOTIVO_SIN_FECHA,
    MOTIVO_VENCIDO,
    _expandir_manuales,
    generar_prevision,
    recuperar_movimientos_proyectables,
)
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026
DESDE = date(EJERCICIO, 9, 16)
HASTA = date(EJERCICIO, 10, 31)


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


# --- FR-006: motivos de exclusion -------------------------------------------


async def test_vencido_cobrado_se_excluye(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 10),
        estado="cobrado",
        recibo_num="R-COBRADO",
    )
    await db_session.commit()

    proyectados, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert proyectados == []
    assert [e["motivo"] for e in excluidos] == [MOTIVO_COBRADO]


async def test_vencido_pendiente_se_excluye(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 1),
        recibo_num="R-VENCIDO",
    )
    await db_session.commit()

    proyectados, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert proyectados == []
    assert [e["motivo"] for e in excluidos] == [MOTIVO_VENCIDO]


async def test_vencido_devuelto_se_excluye(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 20),
        estado="devuelto",
        recibo_num="R-DEVUELTO",
    )
    await db_session.commit()

    _, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert [e["motivo"] for e in excluidos] == [MOTIVO_COBRADO]


async def test_vencido_anulado_se_excluye(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 20),
        estado="anulado",
        recibo_num="R-ANULADO",
    )
    await db_session.commit()

    _, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert [e["motivo"] for e in excluidos] == [MOTIVO_ANULADO]


async def test_saldo_totalmente_cobrado_se_excluye(db_session):
    """Saldo pendiente 0 sin cambio de estado: tampoco genera flujo futuro."""
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 25),
        importe="1000.0000",
        acumulado="1000.0000",
        recibo_num="R-LIQUIDADO",
    )
    await db_session.commit()

    proyectados, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert proyectados == []
    assert [e["motivo"] for e in excluidos] == [MOTIVO_COBRADO]


async def test_saldo_parcial_pendiente_se_proyecta(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 25),
        importe="1000.0000",
        acumulado="600.0000",
        recibo_num="R-PARCIAL",
    )
    await db_session.commit()

    proyectados, excluidos = await recuperar_movimientos_proyectables(
        db_session, empresa_id=EMPRESA, desde_fecha=DESDE, hasta_fecha=HASTA
    )
    assert excluidos == []
    assert proyectados[0]["importe"] == Decimal("400.0000")


# --- Movimientos manuales sin fecha (edge case del spec) -------------------


def test_manual_sin_fecha_se_excluye_con_motivo():
    proyectados, excluidos = _expandir_manuales(
        [{"tipo": "pago", "importe": "1200.0000", "concepto": "Alquiler"}],
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
    )
    assert proyectados == []
    assert [e["motivo"] for e in excluidos] == [MOTIVO_SIN_FECHA]
    assert excluidos[0]["importe"] == Decimal("1200.0000")


def test_manual_con_fecha_entra():
    proyectados, excluidos = _expandir_manuales(
        [
            {
                "tipo": "pago",
                "importe": "1200.0000",
                "fecha_prevista": date(2026, 10, 1),
                "concepto": "Alquiler",
            }
        ],
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
    )
    assert excluidos == []
    assert proyectados[0]["fecha_prevista"] == date(2026, 10, 1)
    assert proyectados[0]["origen"] == "pago_recurrente"


def test_manual_cobro_es_cobro_estimado():
    proyectados, _ = _expandir_manuales(
        [
            {
                "tipo": "cobro",
                "importe": "300.0000",
                "fecha_prevista": date(2026, 10, 5),
            }
        ],
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
    )
    assert proyectados[0]["origen"] == "cobro_estimado"


# --- Los excluidos se persisten con su motivo ------------------------------


async def test_generar_persiste_excluidos_con_motivo(db_session):
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 10),
        estado="cobrado",
        recibo_num="R-COBRADO",
    )
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 30),
        importe="1000.0000",
        recibo_num="R-OK",
    )
    await db_session.commit()

    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
    )
    assert resultado["n_movimientos"] == 1
    motivos = {e["motivo"] for e in resultado["excluidos"]}
    assert motivos == {MOTIVO_COBRADO}

    filas = (await db_session.scalars(select(MovimientoPrevision))).all()
    excluidos = [m for m in filas if not m.incluido]
    incluidos = [m for m in filas if m.incluido]
    assert len(excluidos) == 1
    assert excluidos[0].motivo_exclusion == MOTIVO_COBRADO
    assert excluidos[0].numero_recibo == "R-COBRADO"
    assert len(incluidos) == 1
    assert incluidos[0].motivo_exclusion is None


async def test_excluido_con_saldo_residual_cero_no_rompe_el_check(db_session):
    """Un cobro liquidado deja saldo 0: la columna exige `importe > 0`."""
    await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(2026, 9, 25),
        importe="1000.0000",
        acumulado="1000.0000",
        recibo_num="R-LIQUIDADO",
    )
    await db_session.commit()

    await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
    )
    await db_session.commit()
    filas = (await db_session.scalars(select(MovimientoPrevision))).all()
    assert filas[0].importe == Decimal("0.0001")
    assert filas[0].incluido is False


# --- Validaciones de entrada -------------------------------------------------


async def test_importe_no_positivo_rechazado(db_session):
    with pytest.raises(CashflowError) as exc:
        await generar_prevision(
            db_session,
            empresa_id=EMPRESA,
            desde_fecha=DESDE,
            hasta_fecha=HASTA,
            movimientos_manuales=[
                {"tipo": "pago", "importe": "0", "fecha_prevista": date(2026, 10, 1)}
            ],
        )
    assert exc.value.code == "importe_invalido"
    assert exc.value.status_code == 422


async def test_importe_flotante_rechazado(db_session):
    """SC-005: los importes viajan como cadena decimal, nunca como `float`."""
    with pytest.raises(CashflowError) as exc:
        await generar_prevision(
            db_session,
            empresa_id=EMPRESA,
            desde_fecha=DESDE,
            hasta_fecha=HASTA,
            movimientos_manuales=[
                {"tipo": "pago", "importe": 1200.5, "fecha_prevista": date(2026, 10, 1)}
            ],
        )
    assert exc.value.code == "importe_invalido"


async def test_rango_invertido_rechazado(db_session):
    with pytest.raises(CashflowError) as exc:
        await generar_prevision(
            db_session,
            empresa_id=EMPRESA,
            desde_fecha=HASTA,
            hasta_fecha=DESDE,
        )
    assert exc.value.code == "rango_invalido"


async def test_granularidad_invalida_rechazada(db_session):
    with pytest.raises(CashflowError) as exc:
        await generar_prevision(
            db_session,
            empresa_id=EMPRESA,
            desde_fecha=DESDE,
            hasta_fecha=HASTA,
            granularidad="trimestre",
        )
    assert exc.value.code == "granularidad_invalida"


async def test_tipo_manual_invalido_rechazado(db_session):
    with pytest.raises(CashflowError) as exc:
        await generar_prevision(
            db_session,
            empresa_id=EMPRESA,
            desde_fecha=DESDE,
            hasta_fecha=HASTA,
            movimientos_manuales=[
                {"tipo": "transferencia", "importe": "10", "fecha_prevista": date(2026, 10, 1)}
            ],
        )
    assert exc.value.code == "tipo_invalido"
