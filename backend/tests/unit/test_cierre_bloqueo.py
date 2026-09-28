"""SPEC-026 US3 · T030: bloqueo demodificacion tras el cierre (FR-004/SC-003).

Despues de cerrar el periodo de seguimiento:
- guardar o modificar presupuesto devuelve 409 `periodo_cerrado`;
- cerrar de nuevo el mismo periodo devuelve 409 `periodo_ya_cerrado`;
- el snapshot `Desviacion` no se puede modificar ni borrar (constitucion II).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.budget.cierre_periodo import cerrar_periodo_desviaciones
from services.budget.errores import PresupuestoError
from services.budget.periodos import (
    crear_periodo,
    listar_periodos,
    periodo_bloqueante,
)
from services.budget.presupuesto_service import guardar_presupuesto
from tests.unit.budget_support import (
    cuentas,
    empresa,
    presupuesto_directo,
    publicar_asiento,
)

EMPRESA = 10
OTRA = 20
EJERCICIO = 2026


@pytest.fixture
async def base(db_session):
    await empresa(db_session, EMPRESA)
    await empresa(db_session, OTRA)
    return await cuentas(db_session, EMPRESA)


async def _cerrar(db, plan) -> str:
    periodo = await crear_periodo(
        db,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        fecha_inicio=date(EJERCICIO, 1, 1),
        fecha_fin=date(EJERCICIO, 12, 31),
        actor="test",
    )
    await presupuesto_directo(
        db,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["6400"],
        importe="48000.0000",
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
    await db.flush()
    await cerrar_periodo_desviaciones(
        db, empresa_id=EMPRESA, periodo_id=periodo.id, actor="test"
    )
    return str(periodo.id)


async def test_guardar_presupuesto_tras_el_cierre_es_409(db_session, base):
    await _cerrar(db_session, base)
    await db_session.commit()

    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=base["6400"],
            importe="100.0000",
            actor="test",
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "periodo_cerrado"


async def test_nueva_linea_tras_el_cierre_es_409(db_session, base):
    await _cerrar(db_session, base)
    await db_session.commit()

    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=base["6000"],
            importe="5000.0000",
            actor="test",
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "periodo_cerrado"


async def test_cerrar_un_periodo_ya_cerrado_es_409(db_session, base):
    periodo_id = await _cerrar(db_session, base)
    await db_session.commit()

    with pytest.raises(PresupuestoError) as exc:
        await cerrar_periodo_desviaciones(
            db_session, empresa_id=EMPRESA, periodo_id=periodo_id, actor="test"
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "periodo_ya_cerrado"


async def test_importar_tras_el_cierre_es_409(db_session, base):
    from services.budget.presupuesto_service import importar_presupuesto

    await _cerrar(db_session, base)
    await db_session.commit()

    with pytest.raises(PresupuestoError) as exc:
        await importar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            filas=[{"fila": 1, "codigo_cuenta": "6000", "importe": "1.0000"}],
            actor="test",
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "periodo_cerrado"


async def test_abrir_un_periodo_nuevo_despues_del_cierre(db_session, base):
    """El ciclo continua: con un periodo nuevo abierto se vuelve a presupuestar."""
    await _cerrar(db_session, base)
    await db_session.commit()

    nuevo = await crear_periodo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        fecha_inicio=date(EJERCICIO, 7, 1),
        fecha_fin=date(EJERCICIO, 12, 31),
        actor="test",
    )
    await db_session.commit()
    assert nuevo.numero_periodo == 2
    assert await periodo_bloqueante(db_session, EMPRESA, EJERCICIO) is None

    presupuesto = await guardar_presupuesto(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["6400"],
        importe="52000.0000",
        actor="test",
    )
    await db_session.commit()
    assert Decimal(presupuesto.importe) == Decimal("52000.0000")
    assert str(presupuesto.periodo_id) == str(nuevo.id)


async def test_el_cierre_de_otra_empresa_no_bloquea(db_session, base):
    await _cerrar(db_session, base)
    await db_session.commit()

    assert await periodo_bloqueante(db_session, OTRA, EJERCICIO) is None
    periodos_b = await listar_periodos(db_session, OTRA, EJERCICIO)
    assert periodos_b == []


async def test_snapshot_no_se_puede_actualizar(db_session_factory):
    async with db_session_factory() as session:
        await empresa(session, EMPRESA)
        plan = await cuentas(session, EMPRESA)
        await _cerrar(session, plan)
        await session.commit()

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError) as exc:
            await session.execute(
                text(
                    "UPDATE desviacion SET importe_real = '0.0000' "
                    "WHERE empresa_id = :e"
                ),
                {"e": EMPRESA},
            )
        assert "inmutable" in str(exc.value)


async def test_snapshot_no_se_puede_borrar(db_session_factory):
    async with db_session_factory() as session:
        await empresa(session, EMPRESA)
        plan = await cuentas(session, EMPRESA)
        await _cerrar(session, plan)
        await session.commit()

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError) as exc:
            await session.execute(
                text("DELETE FROM desviacion WHERE empresa_id = :e"), {"e": EMPRESA}
            )
        assert "inmutable" in str(exc.value)


async def test_la_api_no_expone_borrado_ni_edicion_del_snapshot(presupuestos_client):
    """El snapshot del cierre solo se lee: no hay DELETE ni PUT/PATCH de filas."""
    ns = presupuestos_client
    periodo = ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
        },
    )
    assert periodo.status_code == 201
    periodo_id = periodo.json()["periodo_id"]
    assert ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    ).status_code == 200

    assert (
        ns.client.delete(
            f"/api/v1/presupuestos/seguimiento/snapshot?periodo_id={periodo_id}",
            headers=ns.headers(),
        ).status_code
        == 405
    )
    assert (
        ns.client.put(
            f"/api/v1/presupuestos/seguimiento/snapshot?periodo_id={periodo_id}",
            headers=ns.headers(),
        ).status_code
        == 405
    )
