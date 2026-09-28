"""Validaciones de apertura duplicada/cierre previo (SPEC-009 T025-T027, FR-002/004)."""

from __future__ import annotations

from datetime import date

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
from services.cycle.apertura import generar_asiento_apertura
from services.cycle.validacion_previa import (
    CicloError,
    EjercicioCerradoError,
    EjercicioNoDefinidoError,
    EjercicioYaAbiertoError,
    SolapamientoEjerciciosError,
)


async def _con_saldos(db, empresa_id, year, capital="5000.0000"):
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
            debe="0.0000",
            haber=capital,
        )
    )
    db.add(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=entry.id,
            account_id=ids["2100"],
            line_no=2,
            cuenta="2100",
            debe=capital,
            haber="0.0000",
        )
    )
    await db.flush()


def _cerrar(db, empresa_id, year, cerrado=True):
    db.add(
        FiscalYear(
            empresa_id=empresa_id,
            year=year,
            date_start=date(year, 1, 1),
            date_end=date(year, 12, 31),
            is_closed=cerrado,
            cierre_entry_id=None,
        )
    )


def _destino(db, empresa_id, year, inicio=None, fin=None, estado=EjercicioEstado.abierto):
    db.add(
        EjercicioContable(
            empresa_id=empresa_id,
            ejercicio=year,
            fecha_inicio=inicio or date(year, 1, 1),
            fecha_fin=fin or date(year, 12, 31),
            estado=estado,
        )
    )


async def test_cierre_previo_obligatorio(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _con_saldos(db_session, 10, 2026)
    _cerrar(db_session, 10, 2026, cerrado=False)
    _destino(db_session, 10, 2027)
    await db_session.flush()

    try:
        await generar_asiento_apertura(
            db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
        )
        raise AssertionError("debería fallar")
    except Exception as exc:  # noqa: BLE001
        assert isinstance(exc, CicloError)
        assert isinstance(exc, EjercicioCerradoError)


async def test_sin_ejercicio_previo_definido(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    _destino(db_session, 10, 2027)
    await db_session.flush()

    try:
        await generar_asiento_apertura(
            db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
        )
        raise AssertionError("debería fallar")
    except Exception as exc:  # noqa: BLE001
        assert isinstance(exc, EjercicioNoDefinidoError)


async def test_destino_sin_rango_definido(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _con_saldos(db_session, 10, 2026)
    _cerrar(db_session, 10, 2026)
    await db_session.flush()

    try:
        await generar_asiento_apertura(
            db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
        )
        raise AssertionError("debería fallar")
    except Exception as exc:  # noqa: BLE001
        assert isinstance(exc, EjercicioNoDefinidoError)


async def test_rangos_solapados_rechazados(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _con_saldos(db_session, 10, 2026)
    _cerrar(db_session, 10, 2026)
    _destino(db_session, 10, 2027, inicio=date(2026, 12, 1), fin=date(2027, 12, 31))
    await db_session.flush()

    try:
        await generar_asiento_apertura(
            db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
        )
        raise AssertionError("debería fallar")
    except Exception as exc:  # noqa: BLE001
        assert isinstance(exc, SolapamientoEjerciciosError)


async def test_segunda_apertura_rechazada(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _con_saldos(db_session, 10, 2026)
    _cerrar(db_session, 10, 2026)
    _destino(db_session, 10, 2027)
    await db_session.flush()

    primero = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )
    assert primero["estado"] == "con_apertura"

    try:
        await generar_asiento_apertura(
            db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
        )
        raise AssertionError("debería fallar")
    except Exception as exc:  # noqa: BLE001
        assert isinstance(exc, EjercicioYaAbiertoError)