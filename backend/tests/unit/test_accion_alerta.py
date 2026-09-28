"""Acciones sobre la alerta de liquidez (T033, US3/research D6).

`reprogramar_pago` desplaza la fecha prevista de un pago; `incluir_ingreso` crea
un cobro previsto por el deficit; ambas marcan la alerta como `atendida` con
auditoria. `ignorar` la desestima de forma trazable. Una alerta ya resuelta
devuelve 409.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.treasury.movimiento_prevision import (
    MovimientoPrevision,
    TipoMovimientoPrevision,
)
from services.cashflow.alertas import (
    gestionar_alerta,
    ignorar_alerta,
    listar_alertas,
)
from services.cashflow.errores import CashflowError
from services.cashflow.proyeccion import generar_prevision, movimientos_de_prevision
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026
DESDE = date(EJERCICIO, 9, 16)
HASTA = date(EJERCICIO, 9, 16)


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


async def _prevision_con_deficit(db):
    return await generar_prevision(
        db,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {
                "tipo": "pago",
                "importe": "1000.0000",
                "fecha_prevista": date(2026, 9, 16),
                "concepto": "Alquiler",
            }
        ],
    )


async def _primera_alerta(db, prevision_id):
    listado = await listar_alertas(db, empresa_id=EMPRESA, prevision_id=prevision_id)
    return listado["items"][0]


# --- reprogramar_pago --------------------------------------------------------


async def test_reprogramar_pago_desplaza_la_fecha(db_session):
    resultado = await _prevision_con_deficit(db_session)
    alerta = resultado["alertas"][0]
    pago = (
        await db_session.scalars(
            select(MovimientoPrevision).where(
                MovimientoPrevision.prevision_id == resultado["id"]
            )
        )
    ).one()
    assert pago.fecha_prevista == date(2026, 9, 16)

    atendida = await gestionar_alerta(
        db_session,
        empresa_id=EMPRESA,
        alerta_id=alerta.id,
        accion="reprogramar_pago",
        movimiento_id=str(pago.id),
        nueva_fecha="2026-10-15",
        actor="test",
    )
    assert atendida.estado.value == "atendida"
    assert atendida.movimiento_origen_id == pago.id
    assert atendida.atendida_por == "test"
    assert atendida.fecha_atencion is not None

    await db_session.refresh(pago)
    assert pago.fecha_prevista == date(2026, 10, 15)


async def test_reprogramar_usa_el_movimiento_sugerido_por_defecto(db_session):
    """Si el cuerpo no manda `movimiento_id`, se usa el de la propia alerta."""
    resultado = await _prevision_con_deficit(db_session)
    alerta = resultado["alertas"][0]
    assert alerta.movimiento_origen_id is not None

    atendida = await gestionar_alerta(
        db_session,
        empresa_id=EMPRESA,
        alerta_id=alerta.id,
        accion="reprogramar_pago",
        nueva_fecha="2026-10-15",
    )
    assert atendida.estado.value == "atendida"
    movimientos = await movimientos_de_prevision(
        db_session, empresa_id=EMPRESA, prevision_id=resultado["id"]
    )
    assert movimientos[0].fecha_prevista == date(2026, 10, 15)


async def test_reprogramar_sin_fecha_devuelve_422(db_session):
    resultado = await _prevision_con_deficit(db_session)
    alerta = resultado["alertas"][0]
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=alerta.id,
            accion="reprogramar_pago",
        )
    assert exc.value.code == "fecha_requerida"
    assert exc.value.status_code == 422


async def test_reprogramar_una_venta_se_rechaza(db_session):
    """Solo los pagos se reprograman: un cobro no es un gasto aplazable."""
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=HASTA,
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "cobro", "importe": "100.0000", "fecha_prevista": date(2026, 9, 16)},
            {"tipo": "pago", "importe": "500.0000", "fecha_prevista": date(2026, 9, 16)},
        ],
    )
    venta = (
        await db_session.scalars(
            select(MovimientoPrevision).where(
                MovimientoPrevision.prevision_id == resultado["id"],
                MovimientoPrevision.tipo == TipoMovimientoPrevision.cobro,
            )
        )
    ).one()
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=resultado["alertas"][0].id,
            accion="reprogramar_pago",
            movimiento_id=str(venta.id),
            nueva_fecha="2026-10-01",
        )
    assert exc.value.code == "movimiento_no_pago"
    assert exc.value.status_code == 422


async def test_reprogramar_movimiento_de_otra_prevision(db_session):
    primera = await _prevision_con_deficit(db_session)
    segunda = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=DESDE,
        hasta_fecha=date(2026, 10, 31),
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "pago", "importe": "2000.0000", "fecha_prevista": date(2026, 10, 5)}
        ],
    )
    ajenos = await movimientos_de_prevision(
        db_session, empresa_id=EMPRESA, prevision_id=segunda["id"]
    )
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=primera["alertas"][0].id,
            accion="reprogramar_pago",
            movimiento_id=str(ajenos[0].id),
            nueva_fecha="2026-10-20",
        )
    assert exc.value.code == "movimiento_ajeno_a_la_alerta"


async def test_reprogramar_movimiento_inexistente_devuelve_404(db_session):
    resultado = await _prevision_con_deficit(db_session)
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=resultado["alertas"][0].id,
            accion="reprogramar_pago",
            movimiento_id="11111111-1111-1111-1111-111111111111",
            nueva_fecha="2026-10-15",
        )
    assert exc.value.code == "movimiento_no_encontrado"
    assert exc.value.status_code == 404


# --- incluir_ingreso ---------------------------------------------------------


async def test_incluir_ingreso_cubre_el_deficit(db_session):
    resultado = await _prevision_con_deficit(db_session)
    alerta = resultado["alertas"][0]
    assert alerta.importe_deficit == Decimal("1000.0000")

    atendida = await gestionar_alerta(
        db_session,
        empresa_id=EMPRESA,
        alerta_id=alerta.id,
        accion="incluir_ingreso",
        actor="test",
    )
    assert atendida.estado.value == "atendida"

    movimientos = await movimientos_de_prevision(
        db_session, empresa_id=EMPRESA, prevision_id=resultado["id"]
    )
    cobros = [m for m in movimientos if m.tipo is TipoMovimientoPrevision.cobro]
    assert len(cobros) == 1
    # Sin importe explicito se crea por el deficit completo.
    assert cobros[0].importe == Decimal("1000.0000")
    assert cobros[0].origen.value == "cobro_estimado"
    assert cobros[0].fecha_prevista == alerta.fecha


async def test_incluir_ingreso_con_importe_y_fecha(db_session):
    resultado = await _prevision_con_deficit(db_session)
    atendida = await gestionar_alerta(
        db_session,
        empresa_id=EMPRESA,
        alerta_id=resultado["alertas"][0].id,
        accion="incluir_ingreso",
        importe="3000.0000",
        nueva_fecha="2026-10-20",
    )
    assert atendida.estado.value == "atendida"
    movimientos = await movimientos_de_prevision(
        db_session, empresa_id=EMPRESA, prevision_id=resultado["id"]
    )
    cobros = [m for m in movimientos if m.tipo is TipoMovimientoPrevision.cobro]
    assert cobros[0].importe == Decimal("3000.0000")
    assert cobros[0].fecha_prevista == date(2026, 10, 20)


async def test_incluir_ingreso_con_importe_no_positivo(db_session):
    resultado = await _prevision_con_deficit(db_session)
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=resultado["alertas"][0].id,
            accion="incluir_ingreso",
            importe="0",
        )
    assert exc.value.code == "importe_invalido"


# --- ignorar y estados terminales -------------------------------------------


async def test_ignorar_marca_la_alerta_desestimada(db_session):
    resultado = await _prevision_con_deficit(db_session)
    alerta = await _gestionar(db_session, resultado, ignorar_alerta)
    assert alerta.estado.value == "ignorada"
    assert alerta.atendida_por == "test"


async def _gestionar(db, resultado, funcion):
    alerta = resultado["alertas"][0]
    return await funcion(db, empresa_id=EMPRESA, alerta_id=alerta.id, actor="test")


async def test_alerta_ya_atendida_devuelve_409(db_session):
    resultado = await _prevision_con_deficit(db_session)
    alerta = resultado["alertas"][0]
    await gestionar_alerta(
        db_session,
        empresa_id=EMPRESA,
        alerta_id=alerta.id,
        accion="incluir_ingreso",
    )
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=alerta.id,
            accion="incluir_ingreso",
        )
    assert exc.value.code == "alerta_ya_resuelta"
    assert exc.value.status_code == 409


async def test_alerta_ya_ignorada_no_se_puede_atender(db_session):
    resultado = await _prevision_con_deficit(db_session)
    alerta = resultado["alertas"][0]
    await ignorar_alerta(db_session, empresa_id=EMPRESA, alerta_id=alerta.id)
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=alerta.id,
            accion="incluir_ingreso",
        )
    assert exc.value.code == "alerta_ya_resuelta"


async def test_no_se_puede_ignorar_dos_veces(db_session):
    resultado = await _prevision_con_deficit(db_session)
    alerta = resultado["alertas"][0]
    await ignorar_alerta(db_session, empresa_id=EMPRESA, alerta_id=alerta.id)
    with pytest.raises(CashflowError) as exc:
        await ignorar_alerta(db_session, empresa_id=EMPRESA, alerta_id=alerta.id)
    assert exc.value.code == "alerta_ya_resuelta"
    assert exc.value.status_code == 409


async def test_alerta_inexistente_devuelve_404(db_session):
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id="11111111-1111-1111-1111-111111111111",
            accion="incluir_ingreso",
        )
    assert exc.value.code == "alerta_no_encontrada"
    assert exc.value.status_code == 404


async def test_accion_desconocida_devuelve_422(db_session):
    resultado = await _prevision_con_deficit(db_session)
    with pytest.raises(CashflowError) as exc:
        await gestionar_alerta(
            db_session,
            empresa_id=EMPRESA,
            alerta_id=resultado["alertas"][0].id,
            accion="pedir_prestamo",
        )
    assert exc.value.code == "accion_invalida"
    assert exc.value.status_code == 422


async def test_listado_filtrado_por_estado(db_session):
    resultado = await _prevision_con_deficit(db_session)
    await ignorar_alerta(
        db_session,
        empresa_id=EMPRESA,
        alerta_id=resultado["alertas"][0].id,
        actor="test",
    )
    await db_session.commit()
    abiertas = await listar_alertas(db_session, empresa_id=EMPRESA, estado="abierta")
    ignoradas = await listar_alertas(db_session, empresa_id=EMPRESA, estado="ignorada")
    assert abiertas["total"] == 0
    assert ignoradas["total"] == 1
    assert ignoradas["items"][0].estado.value == "ignorada"
