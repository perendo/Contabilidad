"""Aislamiento multi-tenant de los modelos de SPEC-027 (T011, constitucion III).

Crea una prevision, sus movimientos y sus alertas en la empresa A y comprueba que
**ninguna** consulta de la empresa B los ve. El isolation real por API (404 en
detalle, listados vacios, alerta no atendible) vive en
`test_prevision_tenant.py` (T021) y `test_alertas_tenant.py` (T039).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.treasury.alerta_liquidez import (
    AccionSugeridaLiquidez,
    AlertaLiquidez,
    EstadoAlertaLiquidez,
)
from models.treasury.efe import BloqueEFE, InformeEFE, LineaEFE
from models.treasury.movimiento_prevision import (
    MovimientoPrevision,
    OrigenMovimientoPrevision,
    TipoMovimientoPrevision,
)
from models.treasury.prevision import (
    EstadoPrevision,
    GranularidadPrevision,
    PrevisionTesoreria,
)
from services.cashflow.alertas import listar_alertas, obtener_alerta
from services.cashflow.efe import informe_formulado
from services.cashflow.proyeccion import (
    listar_previsiones,
    movimientos_de_prevision,
    obtener_prevision,
)
from tests.unit import cashflow_support as soporte

A = soporte.A
B = soporte.B
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _empresas(db_session_factory):
    async with db_session_factory() as session:
        for empresa_id in (A, B):
            await soporte.empresa(session, empresa_id)
        await session.commit()


async def _prevision_de_A(db) -> PrevisionTesoreria:
    prevision = PrevisionTesoreria(
        empresa_id=A,
        numero_prevision=1,
        desde_fecha=date(EJERCICIO, 9, 16),
        hasta_fecha=date(EJERCICIO, 10, 31),
        granularidad=GranularidadPrevision.dia,
        saldo_inicial=Decimal("100.0000"),
        saldo_final=Decimal("-900.0000"),
        estado=EstadoPrevision.generada,
    )
    db.add(prevision)
    await db.flush()
    db.add(
        MovimientoPrevision(
            empresa_id=A,
            prevision_id=prevision.id,
            origen=OrigenMovimientoPrevision.pago_recurrente,
            tipo=TipoMovimientoPrevision.pago,
            importe=Decimal("1000.0000"),
            fecha_prevista=date(EJERCICIO, 10, 1),
            incluido=True,
        )
    )
    db.add(
        AlertaLiquidez(
            empresa_id=A,
            prevision_id=prevision.id,
            fecha=date(EJERCICIO, 10, 1),
            saldo_proyectado=Decimal("-900.0000"),
            importe_deficit=Decimal("900.0000"),
            estado=EstadoAlertaLiquidez.abierta,
            accion_sugerida=AccionSugeridaLiquidez.reprogramar_pago,
        )
    )
    await db.flush()
    return prevision


async def test_prevision_de_A_no_la_ve_B(db_session):
    prevision = await _prevision_de_A(db_session)
    await db_session.commit()

    assert await obtener_prevision(db_session, empresa_id=A, prevision_id=prevision.id)
    assert await obtener_prevision(db_session, empresa_id=B, prevision_id=prevision.id) is None


async def test_listado_de_B_no_devuelve_previsiones_de_A(db_session):
    await _prevision_de_A(db_session)
    await db_session.commit()

    de_a = await listar_previsiones(db_session, empresa_id=A)
    de_b = await listar_previsiones(db_session, empresa_id=B)
    assert de_a["total"] == 1
    assert de_b["total"] == 0
    assert de_b["items"] == []


async def test_movimientos_de_B_no_ve_los_de_A(db_session):
    prevision = await _prevision_de_A(db_session)
    await db_session.commit()

    propios = await movimientos_de_prevision(
        db_session, empresa_id=B, prevision_id=prevision.id
    )
    assert propios == []


async def test_alerta_de_A_no_la_ve_B(db_session):
    prevision = await _prevision_de_A(db_session)
    await db_session.commit()

    de_b = await listar_alertas(db_session, empresa_id=B, prevision_id=prevision.id)
    assert de_b["total"] == 0
    assert de_b["items"] == []

    alerta_a = (await listar_alertas(db_session, empresa_id=A))["items"][0]
    assert await obtener_alerta(db_session, empresa_id=B, alerta_id=alerta_a.id) is None


async def test_efe_de_A_no_lo_ve_B(db_session):
    informe = InformeEFE(empresa_id=A, ejercicio=EJERCICIO, cuadre=True)
    db_session.add(informe)
    await db_session.flush()
    db_session.add(
        LineaEFE(
            empresa_id=A,
            informe_id=informe.id,
            bloque=BloqueEFE.operativa,
            cuenta_id=1,
            codigo_cuenta="6400",
            importe=Decimal("100.0000"),
        )
    )
    await db_session.commit()

    assert await informe_formulado(db_session, empresa_id=A, ejercicio=EJERCICIO)
    assert await informe_formulado(db_session, empresa_id=B, ejercicio=EJERCICIO) is None


async def test_seleccion_cruda_por_empresa_no_mezcla(db_session):
    """Sin filtro de `empresa_id` la consulta cruzaria datos: debe existir columna."""
    await _prevision_de_A(db_session)
    await db_session.commit()
    propias = (
        await db_session.scalars(
            select(PrevisionTesoreria).where(PrevisionTesoreria.empresa_id == A)
        )
    ).all()
    assert len(propias) == 1
    assert propias[0].empresa_id == A
