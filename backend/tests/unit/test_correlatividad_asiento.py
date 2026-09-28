"""Unit tests SPEC-002 T015: correlatividad del número de asiento (FR-005/SC-006)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from services.journal.entry_service import AsientoError, asentar, crear_borrador


async def _cuenta_ids(db, empresa_id: int) -> tuple[int, int]:
    c4300 = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "4300"
        )
    )
    c5720 = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "5720"
        )
    )
    return c4300.id, c5720.id


async def _asentar_n(db, empresa_id: int, n: int, anio: int = 2026) -> list[int]:
    c4300, c5720 = await _cuenta_ids(db, empresa_id)
    numeros: list[int] = []
    for i in range(1, n + 1):
        borrador = await crear_borrador(
            db,
            empresa_id=empresa_id,
            fecha=date(anio, 1, i),
            concepto=f"Asiento {i}",
            lineas=[
                {"account_id": c4300, "debit": "100", "credit": "0", "detail": "cliente"},
                {"account_id": c5720, "debit": "0", "credit": "100", "detail": "banco"},
            ],
        )
        await db.flush()
        asentado = await asentar(db, empresa_id=empresa_id, entry_id=borrador.id)
        numeros.append(asentado.numero_asiento)
    return numeros


async def test_secuencia_sin_saltos(motor_db_session):
    numeros = await _asentar_n(motor_db_session, 10, 3)
    assert numeros == [1, 2, 3]


async def test_ejercicio_distinto_independiente(motor_db_session):
    n2026 = await _asentar_n(motor_db_session, 10, 1, anio=2026)
    n2027 = await _asentar_n(motor_db_session, 10, 2, anio=2027)
    assert n2026 == [1]
    assert n2027 == [1, 2]


async def test_secuencia_por_empresa_independiente(motor_db_session):
    a = await _asentar_n(motor_db_session, 10, 2)
    b = await _asentar_n(motor_db_session, 20, 1)
    assert a == [1, 2]
    assert b == [1]


async def test_rollback_no_reutiliza_numero(motor_db_session):
    await _asentar_n(motor_db_session, 10, 1)
    # Intento de asentar en la empresa 20 un borrador de la empresa 10 → 404
    c4300, c5720 = await _cuenta_ids(motor_db_session, 10)
    borrador = await crear_borrador(
        motor_db_session,
        empresa_id=10,
        fecha=date(2026, 1, 2),
        concepto="Venta",
        lineas=[
            {"account_id": c4300, "debit": "100", "credit": "0"},
            {"account_id": c5720, "debit": "0", "credit": "100"},
        ],
    )
    await motor_db_session.flush()
    with pytest.raises(AsientoError) as exc:
        await asentar(motor_db_session, empresa_id=20, entry_id=borrador.id)
    assert exc.value.code == "asiento_no_encontrado"
    # El siguiente asiento de la empresa 10 sigue usando el número correlativo 2
    siguientes = await _asentar_n(motor_db_session, 10, 1)
    assert siguientes == [2]