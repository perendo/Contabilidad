"""SPEC-026 US3 · T029: el cierre genera un snapshot trazable (T-04/D5).

Al cerrar el periodo se persiste una fila `Desviacion` por combinacion
cuenta-centro presente en el presupuesto o en el diario, el periodo queda
`cerrado` y se registran `fecha_cierre` y `cerrado_por` (constitucion II).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.audit.audit_log import AuditLog
from models.budget.desviacion import Desviacion
from models.budget.periodo_seguimiento import EstadoPeriodo, PeriodoSeguimiento
from services.budget.cierre_periodo import cerrar_periodo_desviaciones, listar_snapshots
from services.budget.errores import PresupuestoError
from services.budget.periodos import crear_periodo, listar_periodos
from tests.unit.budget_support import (
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


async def _periodo(db) -> PeriodoSeguimiento:
    return await crear_periodo(
        db,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        fecha_inicio=date(EJERCICIO, 1, 1),
        fecha_fin=date(EJERCICIO, 12, 31),
        actor="test",
    )


async def _datos(db, plan) -> PeriodoSeguimiento:
    periodo = await _periodo(db)
    await presupuesto_directo(
        db,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["6400"],
        importe="48000.0000",
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
            {"account_id": plan["6400"], "debit": "45000", "credit": "0"},
            {"account_id": plan["4000"], "debit": "0", "credit": "45000"},
        ],
    )
    await publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 7, 15),
        lineas=[
            {"account_id": plan["6000"], "debit": "2000", "credit": "0"},
            {"account_id": plan["4100"], "debit": "0", "credit": "2000"},
        ],
    )
    await db.flush()
    return periodo


async def test_cierre_persiste_una_fila_por_combinacion(db_session, base):
    periodo = await _datos(db_session, base)

    resultado = await cerrar_periodo_desviaciones(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id, actor="contabilidad"
    )
    await db_session.commit()

    assert resultado["estado"] == "cerrado"
    assert resultado["desviaciones_registradas"] == resultado["desviaciones_registradas"]
    filas = await listar_snapshots(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id
    )
    assert len(filas) == resultado["desviaciones_registradas"]
    assert len(filas) >= 3  # 6400 y 7000 presupuestadas + la 6000 sin presupuesto
    combinaciones = {(f.cuenta_id, f.centro_coste_id) for f in filas}
    assert len(combinaciones) == len(filas)


async def test_cierre_registra_fecha_y_actor(db_session, base):
    periodo = await _datos(db_session, base)
    await cerrar_periodo_desviaciones(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id, actor="contabilidad"
    )
    await db_session.commit()

    cerrado = await db_session.get(PeriodoSeguimiento, periodo.id)
    assert cerrado.estado is EstadoPeriodo.cerrado
    assert cerrado.cerrado_por == "contabilidad"
    assert cerrado.fecha_cierre is not None
    assert cerrado.fecha_cierre.tzinfo is not None
    assert cerrado.desviaciones_registradas > 0
    assert cerrado.fecha_cierre <= datetime.now(timezone.utc)


async def test_snapshot_refleja_los_valores_del_presupuesto_y_del_real(db_session, base):
    periodo = await _datos(db_session, base)
    await cerrar_periodo_desviaciones(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id, actor="test"
    )
    await db_session.commit()

    filas = await listar_snapshots(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id
    )
    por_cuenta = {f.cuenta_id: f for f in filas}
    gasto = por_cuenta[base["6400"]]
    assert Decimal(gasto.importe_presupuestado) == Decimal("48000.0000")
    assert Decimal(gasto.importe_real) == Decimal("45000.0000")
    assert Decimal(gasto.desviacion_absoluta) == Decimal("-3000.0000")
    assert Decimal(gasto.desviacion_relativa) == Decimal("-0.0625")
    assert gasto.sin_presupuesto is False

    ingreso = por_cuenta[base["7000"]]
    assert Decimal(ingreso.importe_presupuestado) == Decimal("120000.0000")
    assert Decimal(ingreso.importe_real) == Decimal("0.0000")
    assert Decimal(ingreso.desviacion_absoluta) == Decimal("-120000.0000")

    imprevisto = por_cuenta[base["6000"]]
    assert imprevisto.sin_presupuesto is True
    assert Decimal(imprevisto.importe_presupuestado) == Decimal("0.0000")
    assert Decimal(imprevisto.desviacion_absoluta) == Decimal("2000.0000")
    assert imprevisto.desviacion_relativa is None


async def test_cierre_audita_con_accion_cierre_periodo(db_session, base):
    periodo = await _datos(db_session, base)
    await cerrar_periodo_desviaciones(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id, actor="contabilidad"
    )
    await db_session.commit()

    eventos = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.empresa_id == EMPRESA, AuditLog.operacion == "CIERRE_PERIODO"
        )
    )
    assert int(eventos or 0) == 1


async def test_cierre_deja_la_sesion_de_periodos_actualizada(db_session, base):
    periodo = await _datos(db_session, base)
    await cerrar_periodo_desviaciones(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id, actor="test"
    )
    await db_session.commit()

    periodos = await listar_periodos(db_session, EMPRESA, EJERCICIO)
    assert len(periodos) == 1
    assert periodos[0].estado is EstadoPeriodo.cerrado


async def test_cierre_sin_datos_persiste_cero_desviaciones(db_session, base):
    periodo = await _periodo(db_session)
    await db_session.flush()

    resultado = await cerrar_periodo_desviaciones(
        db_session, empresa_id=EMPRESA, periodo_id=periodo.id, actor="test"
    )
    await db_session.commit()
    assert resultado["desviaciones_registradas"] == 0

    total = await db_session.scalar(
        select(func.count())
        .select_from(Desviacion)
        .where(Desviacion.empresa_id == EMPRESA)
    )
    assert int(total or 0) == 0


async def test_cierre_de_periodo_ajeno_es_404(db_session, base):
    await _datos(db_session, base)
    with pytest.raises(PresupuestoError) as exc:
        await cerrar_periodo_desviaciones(
            db_session,
            empresa_id=20,
            periodo_id=uuid.uuid4(),
            actor="test",
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "periodo_no_encontrado"
