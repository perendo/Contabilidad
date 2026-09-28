"""Anulación y regeneración de la apertura (SPEC-009 T018-T020, FR-006)."""

from __future__ import annotations

import uuid
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
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado
from services.cycle.apertura import (
    anular_apertura,
    generar_asiento_apertura,
    regenerar_apertura,
)
from services.cycle.validacion_previa import CicloError, SinAperturaError


async def _contexto_cerrado(db, empresa_id, year):
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
        ejercicio=year,
        fecha=date(year, 6, 30),
        tipo=JournalEntryTipo.GENERAL,
        concepto=f"Saldos {year}",
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
            year=year,
            date_start=date(year, 1, 1),
            date_end=date(year, 12, 31),
            is_closed=True,
            cierre_entry_id=None,
        )
    )
    db.add(
        EjercicioContable(
            empresa_id=empresa_id,
            ejercicio=year + 1,
            fecha_inicio=date(year + 1, 1, 1),
            fecha_fin=date(year + 1, 12, 31),
            estado=EjercicioEstado.abierto,
        )
    )
    await db.flush()


async def test_anulacion_genera_reversal_enlazado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _contexto_cerrado(db_session, 10, 2026)
    await db_session.flush()

    original = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    resultado = await anular_apertura(
        db_session, empresa_id=10, ejercicio=2027, actor="ana"
    )

    assert resultado["estado"] == "apertura_anulada"
    assert resultado["asiento_anulacion_id"] != original["asiento_id"]

    reversal = await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.id == uuid.UUID(resultado["asiento_anulacion_id"])
        )
    )
    assert reversal is not None
    assert reversal.tipo == JournalEntryTipo.OPENING_REVERSAL
    assert reversal.original_id is not None
    assert reversal.estado == JournalEntryEstado.POSTED
    assert reversal.numero_asiento == 2

    destino = await db_session.scalar(
        select(EjercicioContable).where(
            EjercicioContable.empresa_id == 10, EjercicioContable.ejercicio == 2027
        )
    )
    assert destino.estado == EjercicioEstado.abierto
    assert destino.apertura_entry_id is not None
    assert destino.apertura_reversal_entry_id == reversal.id


async def test_reversal_invierte_lineas(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _contexto_cerrado(db_session, 10, 2026)
    await db_session.flush()

    original = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    resultado = await anular_apertura(
        db_session, empresa_id=10, ejercicio=2027, actor="ana"
    )

    lineas_orig = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == uuid.UUID(original["asiento_id"])
            )
        )
    ).all()
    lineas_rev = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == uuid.UUID(resultado["asiento_anulacion_id"])
            )
        )
    ).all()
    assert len(lineas_rev) == len(lineas_orig)
    for la, lb in zip(lineas_orig, lineas_rev):
        assert lb.cuenta == la.cuenta
        assert lb.debe == la.haber
        assert lb.haber == la.debe

    total_debe = sum(l.debe for l in lineas_rev)
    total_haber = sum(l.haber for l in lineas_rev)
    assert total_debe == total_haber


async def test_anulacion_sin_apertura_error(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _contexto_cerrado(db_session, 10, 2026)
    await db_session.flush()

    try:
        await anular_apertura(db_session, empresa_id=10, ejercicio=2027, actor="ana")
        raise AssertionError("debería fallar")
    except Exception as exc:  # noqa: BLE001
        assert isinstance(exc, CicloError)
        assert isinstance(exc, SinAperturaError)
        assert exc.code == "sin_apertura"


async def test_original_no_se_modifica_tras_anular(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _contexto_cerrado(db_session, 10, 2026)
    await db_session.flush()

    original = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    await anular_apertura(db_session, empresa_id=10, ejercicio=2027, actor="ana")

    entry = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == uuid.UUID(original["asiento_id"]))
    )
    assert entry.tipo == JournalEntryTipo.OPENING
    assert entry.numero_asiento == 1
    assert entry.original_id is None
    assert entry.estado == JournalEntryEstado.POSTED


async def test_regeneracion_trans_anulacion(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _contexto_cerrado(db_session, 10, 2026)
    await db_session.flush()

    original_1 = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    await anular_apertura(db_session, empresa_id=10, ejercicio=2027, actor="ana")
    regenerada = await regenerar_apertura(
        db_session, empresa_id=10, ejercicio=2027, actor="ana"
    )

    assert regenerada["regenerada"] is True
    assert regenerada["asiento_id"] != original_1["asiento_id"]
    assert regenerada["numero_asiento"] == 3
    assert regenerada["estado"] == "con_apertura"

    filas = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == uuid.UUID(regenerada["asiento_id"])
            )
        )
    ).all()
    assert [f.cuenta for f in filas] == ["1110", "2100"]