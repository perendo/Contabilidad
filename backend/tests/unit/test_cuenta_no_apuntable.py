"""Unit tests SPEC-002 T013: cuentas no apuntables / inexistentes / de otra empresa (FR-003)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from services.journal.entry_service import AsientoError, crear_borrador


async def _cuenta_inactiva(db, empresa_id: int) -> int:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "5720"
        )
    )
    cuenta.is_active = False
    await db.flush()
    return cuenta.id


async def test_cuenta_inexistente_422(journal_api):
    respuesta = journal_api.crear(
        lineas=[
            {"account_id": 999999, "debit": "100", "credit": "0"},
            {"account_id": journal_api.cuentas["a"]["5720"], "debit": "0", "credit": "100"},
        ]
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "cuenta_no_apuntable"


async def test_cuenta_de_rango_bajo_no_apuntable(journal_api):
    """Cuenta de 3 dígitos (nivel < 4) no es apuntable (is_selectable=0)."""
    c = journal_api.cuentas["a"]
    respuesta = journal_api.crear(
        lineas=[
            {"account_id": c["430"], "debit": "100", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "100"},
        ]
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "cuenta_no_apuntable"


async def test_cuenta_inactiva_422(motor_db_session):
    c4300 = await motor_db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 10, AccountPlan.code == "4300")
    )
    c5720 = await _cuenta_inactiva(motor_db_session, 10)
    lineas = [
        {"account_id": c4300.id, "debit": "100", "credit": "0"},
        {"account_id": c5720, "debit": "0", "credit": "100"},
    ]
    with pytest.raises(AsientoError) as exc:
        await crear_borrador(
            motor_db_session, empresa_id=10, fecha=__import__("datetime").date(2026, 1, 15),
            concepto="Test", lineas=lineas,
        )
    assert exc.value.code == "cuenta_no_apuntable"


async def test_cuenta_de_otra_empresa_403(journal_api):
    """Línea con cuenta de la empresa B presentada por A → 403 (misma sesión)."""
    c_b = journal_api.cuentas["b"]
    respuesta = journal_api.crear(
        lineas=[
            {"account_id": c_b["4300"], "debit": "100", "credit": "0"},
            {"account_id": journal_api.cuentas["a"]["5720"], "debit": "0", "credit": "100"},
        ]
    )
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"]["code"] == "cuenta_otra_empresa"


async def test_cuenta_otra_empresa_servicio(motor_db_session):
    cuenta_b = (
        await motor_db_session.scalar(
            select(AccountPlan).where(AccountPlan.tenant_id == 20, AccountPlan.code == "5720")
        )
    ).id
    c_a = await motor_db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 10, AccountPlan.code == "4300")
    )
    lineas = [
        {"account_id": c_a.id, "debit": "100", "credit": "0"},
        {"account_id": cuenta_b, "debit": "0", "credit": "100"},
    ]
    with pytest.raises(AsientoError) as exc:
        await crear_borrador(
            motor_db_session, empresa_id=10, fecha=__import__("datetime").date(2026, 1, 15),
            concepto="Test", lineas=lineas,
        )
    assert exc.value.code == "cuenta_otra_empresa"