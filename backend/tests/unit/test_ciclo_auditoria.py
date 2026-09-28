"""Auditoría del ciclo contable en la misma transacción (SPEC-009 T033)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from conftest import sembrar_empresa_pgc
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.audit.audit_log import AuditLog
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado
from services.cycle.apertura import anular_apertura, generar_asiento_apertura


async def _escenario(db, empresa_id):
    ids = {
        code: ident
        for code, ident in (
            await db.execute(
                select(AccountPlan.code, AccountPlan.id).where(
                    AccountPlan.tenant_id == empresa_id,
                    AccountPlan.is_active.is_(True),
                )
            )
        ).all()
    }
    entry = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=2026,
        fecha=date(2026, 6, 30),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Saldos 2026",
        estado=JournalEntryEstado.POSTED,
        numero_asiento=1,
    )
    db.add(entry)
    await db.flush()
    db.add(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=entry.id,
            account_id=ids["1110"],
            line_no=1,
            cuenta="1110",
            debe=Decimal("0.0000"),
            haber=Decimal("5000.0000"),
        )
    )
    db.add(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=entry.id,
            account_id=ids["2100"],
            line_no=2,
            cuenta="2100",
            debe=Decimal("5000.0000"),
            haber=Decimal("0.0000"),
        )
    )
    db.add(
        FiscalYear(
            empresa_id=empresa_id,
            year=2026,
            date_start=date(2026, 1, 1),
            date_end=date(2026, 12, 31),
            is_closed=True,
            cierre_entry_id=None,
        )
    )
    db.add(
        EjercicioContable(
            empresa_id=empresa_id,
            ejercicio=2027,
            fecha_inicio=date(2027, 1, 1),
            fecha_fin=date(2027, 12, 31),
            estado=EjercicioEstado.abierto,
        )
    )
    await db.flush()


async def test_auditoria_apertura_y_anulacion(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _escenario(db_session, 10)
    await db_session.flush()

    await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    await db_session.flush()

    filas = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.empresa_id == 10,
                AuditLog.operacion.in_(["APERTURA", "ANULAR_APERTURA"]),
            )
        )
    ).all()
    assert len(filas) == 1
    assert filas[0].operacion == "APERTURA"
    assert filas[0].usuario == "ana"
    assert filas[0].entidad == "journal_entry"
    assert "2027" in filas[0].payload

    await anular_apertura(db_session, empresa_id=10, ejercicio=2027, actor="ana")
    await db_session.flush()

    filas = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.empresa_id == 10,
                AuditLog.operacion.in_(["APERTURA", "ANULAR_APERTURA"]),
            )
        )
    ).all()
    assert [f.operacion for f in filas] == ["APERTURA", "ANULAR_APERTURA"]