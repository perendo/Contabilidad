"""SPEC-026 US1 · T011: rechazo de duplicados en la combinacion (FR-005).

Insertar dos veces la misma combinacion `(empresa, ejercicio, cuenta, centro)`
debe rechazarse. El servicio devuelve 422 `duplicado_identico`; la garantia
definitiva vive en los indices parciales UNIQUE de `presupuesto`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from models.budget.presupuesto import Presupuesto, TipoPresupuesto
from services.budget.errores import PresupuestoError
from services.budget.presupuesto_service import guardar_presupuesto
from services.budget.utils import c4
from tests.unit.budget_support import (
    crear_centro,
    crear_periodo_abierto,
    cuentas,
    empresa,
    presupuesto_directo,
)

EMPRESA = 10
EJERCICIO = 2026


@pytest.fixture
async def base(db_session):
    await empresa(db_session, EMPRESA)
    return await cuentas(db_session, EMPRESA)


async def test_duplicado_identico_es_422(db_session, base):
    cuenta = base["6400"]
    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=cuenta,
        importe="48000.0000",
    )
    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=cuenta,
            importe="48000.0000",
            tipo="gasto",
            actor="test",
        )
    assert exc.value.code == "duplicado_identico"
    assert exc.value.status_code == 422


async def test_importe_distinto_actualiza_la_misma_linea(db_session, base):
    cuenta = base["6400"]
    primera = await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=cuenta,
        importe="48000.0000",
    )
    await db_session.commit()

    segunda = await guardar_presupuesto(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=cuenta,
        importe="50000.0000",
        tipo="gasto",
        actor="test",
    )
    await db_session.commit()

    assert primera.id == segunda.id
    assert c4(segunda.importe) == Decimal("50000.0000")
    total = await db_session.scalar(
        select(func.count())
        .select_from(Presupuesto)
        .where(Presupuesto.empresa_id == EMPRESA)
    )
    assert int(total or 0) == 1


async def test_unicidad_sin_centro_en_la_base_de_datos(db_session, base):
    """Prueba directa del indice: dos INSERT con la misma combinacion sin centro."""
    cuenta = base["6400"]
    await crear_periodo_abierto(db_session, EMPRESA, EJERCICIO)
    for _ in range(2):
        db_session.add(
            Presupuesto(
                empresa_id=EMPRESA,
                ejercicio=EJERCICIO,
                cuenta_id=cuenta,
                importe=c4(Decimal(1)),
                tipo=TipoPresupuesto.gasto,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_unicidad_con_centro_en_la_base_de_datos(db_session, base):
    cuenta = base["6400"]
    centro = await crear_centro(db_session, EMPRESA)
    await crear_periodo_abierto(db_session, EMPRESA, EJERCICIO)
    for _ in range(2):
        db_session.add(
            Presupuesto(
                empresa_id=EMPRESA,
                ejercicio=EJERCICIO,
                cuenta_id=cuenta,
                centro_coste_id=centro,
                importe=c4(Decimal(1)),
                tipo=TipoPresupuesto.gasto,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_ingresos_tienen_clave_propia(db_session, base):
    """7000 (grupo 7) no colisiona con 6400 (grupo 6) ni con sus homonimos."""
    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["6400"],
        importe="48000.0000",
    )
    await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["7000"],
        importe="120000.0000",
        tipo="ingreso",
    )
    await db_session.commit()
    total = await db_session.scalar(
        select(func.count())
        .select_from(Presupuesto)
        .where(Presupuesto.empresa_id == EMPRESA)
    )
    assert int(total or 0) == 2
