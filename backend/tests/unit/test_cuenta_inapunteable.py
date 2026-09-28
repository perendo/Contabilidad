"""SPEC-026 US1 · T012: rechazo de cuentas no apuntables o ajenas.

Intentar presupuestar una cuenta de nivel 2 (`is_selectable = false`) o una
cuenta de otra empresa debe devolver 422. La cuenta del PGC que se usa en el
quickstart (6400, nivel 4) si es valida.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from services.budget.errores import PresupuestoError
from services.budget.presupuesto_service import guardar_presupuesto, validar_cuenta
from tests.unit.budget_support import cuentas, empresa, presupuesto_directo

EMPRESA = 10
OTRA = 20
EJERCICIO = 2026


@pytest.fixture
async def base(db_session):
    await empresa(db_session, EMPRESA)
    await empresa(db_session, OTRA)
    return await cuentas(db_session, EMPRESA)


async def _cuenta_no_apunteable(db, codigo: str, empresa_id: int = EMPRESA) -> int:
    """Fuerza `is_selectable = false` en una cuenta que el seed marca apuntable."""
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == codigo
        )
    )
    assert cuenta is not None, f"falta la cuenta {codigo}"
    cuenta.is_selectable = False
    await db.flush()
    return int(cuenta.id)


async def test_cuenta_nivel_2_no_apuntable_es_422(db_session, base):
    """Una cuenta de nivel 2 (`is_selectable = false`) no admite presupuesto."""
    nivel2 = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == EMPRESA, AccountPlan.code == "64", AccountPlan.level == 2
        )
    )
    assert nivel2 is not None
    assert nivel2.is_selectable is False

    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=int(nivel2.id),
            importe="1000.0000",
            actor="test",
        )
    assert exc.value.code == "cuenta_inapunteable"
    assert exc.value.status_code == 422


async def test_cuenta_desactivada_es_422(db_session, base):
    cuenta_id = await _cuenta_no_apunteable(db_session, "6400")
    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=cuenta_id,
            importe="1000.0000",
            actor="test",
        )
    assert exc.value.code == "cuenta_inapunteable"


async def test_cuenta_inexistente_es_422(db_session, base):
    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=99999999,
            importe="1000.0000",
            actor="test",
        )
    assert exc.value.code == "cuenta_no_encontrada"
    assert exc.value.status_code == 422


async def test_cuenta_de_otra_empresa_es_422(db_session, base):
    """Constitucion III: una cuenta de la empresa 20 no se presupuesta en la 10."""
    plan_otra = await cuentas(db_session, OTRA)
    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=plan_otra["6400"],
            importe="1000.0000",
            actor="test",
        )
    assert exc.value.code == "cuenta_no_encontrada"
    assert plan_otra["6400"] != base["6400"]


async def test_cuenta_apunteable_se_acepta(db_session, base):
    cuenta = await validar_cuenta(db_session, EMPRESA, base["6400"])
    assert cuenta.code == "6400"
    presupuesto = await presupuesto_directo(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=base["6400"],
        importe="48000.0000",
    )
    assert str(presupuesto.importe) == "48000.0000"


async def test_centro_de_otra_empresa_es_422(db_session, base):
    from services.budget.errores import PresupuestoError as PE
    from tests.unit.budget_support import crear_centro

    centro_ajeno = await crear_centro(db_session, OTRA, codigo="CC-77", nombre="Ajeno")
    with pytest.raises(PE) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=base["6400"],
            centro_coste_id=centro_ajeno,
            importe="48000.0000",
            actor="test",
        )
    assert exc.value.code == "centro_no_encontrado"


async def test_importe_con_mas_de_4_decimales_es_422(db_session, base):
    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=base["6400"],
            importe="48000.00001",
            actor="test",
        )
    assert exc.value.code == "precision_invalida"


async def test_tipo_incoherente_con_el_grupo_es_422(db_session, base):
    with pytest.raises(PresupuestoError) as exc:
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=base["6400"],
            importe="48000.0000",
            tipo="ingreso",
            actor="test",
        )
    assert exc.value.code == "tipo_incoherente"
