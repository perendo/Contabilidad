"""Integration tests SPEC-002 T014: atomicidad cabecera+líneas (FR-004).

Si una línea falla, no queda cabecera huérfana ni líneas parciales; si el
asentado falla, el borrador permanece DRAFT sin número ni auditoría POSTED.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.audit.audit_log import AuditLog
from services.journal.entry_service import AsientoError, asentar, crear_borrador


async def test_fallo_validacion_linea_no_deja_rastro(motor_db_session):
    lineas = [
        {"account_id": 999999, "debit": "100", "credit": "0", "detail": "inválida"},
        {"account_id": 0, "debit": "0", "credit": "100", "detail": "banco"},
    ]
    with pytest.raises(AsientoError):
        await crear_borrador(
            motor_db_session, empresa_id=10, fecha=date(2026, 1, 15), concepto="Test",
            lineas=lineas,
        )
    assert await motor_db_session.scalar(select(func.count()).select_from(JournalEntry)) == 0
    assert (
        await motor_db_session.scalar(select(func.count()).select_from(JournalEntryLine)) == 0
    )


async def test_asentado_desbalanceado_deja_borrador_intacto(motor_db_session):
    c4300, c5720 = await _cuenta_ids(motor_db_session, 10)
    borrador = await crear_borrador(
        motor_db_session,
        empresa_id=10,
        fecha=date(2026, 1, 15),
        concepto="Venta",
        lineas=[
            {"account_id": c4300, "debit": "100", "credit": "0", "detail": "cliente"},
            {"account_id": c5720, "debit": "0", "credit": "100", "detail": "banco"},
        ],
    )
    await motor_db_session.flush()
    # Desbalancear una línea directamente en DB
    linea = await motor_db_session.scalar(
        select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == borrador.id)
    )
    linea.debe = "50"
    await motor_db_session.flush()
    with pytest.raises(AsientoError) as exc:
        await asentar(motor_db_session, empresa_id=10, entry_id=borrador.id)
    assert exc.value.code == "desbalanceado"

    entrada = await motor_db_session.get(JournalEntry, borrador.id)
    assert entrada.estado == JournalEntryEstado.DRAFT
    assert entrada.numero_asiento is None
    posted_audit = await motor_db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.empresa_id == 10, AuditLog.operacion == "POSTED")
    )
    assert posted_audit == 0


async def _cuenta_ids(db, empresa_id: int) -> tuple[int, int]:
    c4300 = await db.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == "4300")
    )
    c5720 = await db.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == "5720")
    )
    return c4300.id, c5720.id