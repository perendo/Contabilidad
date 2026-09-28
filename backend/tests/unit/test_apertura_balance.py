"""Balance del asiento de apertura (SPEC-009 T010, FR-003).

Solo se abren cuentas patrimoniales de grupo 1-3; las 6-7 (resultado) del
cierre previo nunca se abren; Debe == Haber con Decimal exacto.
"""

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
from services.cycle.apertura import generar_asiento_apertura


async def _cerrar_con_saldos(db, empresa_id, year, lineas):
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
    for i, (codigo, debe, haber) in enumerate(lineas, start=1):
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=entry.id,
                account_id=ids[codigo],
                line_no=i,
                cuenta=codigo,
                debe=Decimal(debe),
                haber=Decimal(haber),
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
    await db.flush()


async def _definir_destino(db, empresa_id, year):
    db.add(
        EjercicioContable(
            empresa_id=empresa_id,
            ejercicio=year,
            fecha_inicio=date(year, 1, 1),
            fecha_fin=date(year, 12, 31),
            estado=EjercicioEstado.abierto,
        )
    )
    await db.flush()


async def test_solo_grupos_1_3_y_balance(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _cerrar_con_saldos(
        db_session,
        10,
        2026,
        [
            ("1110", "0", "5000.0000"),
            ("2100", "5000.0000", "0"),
            ("6400", "1000.0000", "0"),
            ("7000", "0", "1000.0000"),
        ],
    )
    await _definir_destino(db_session, 10, 2027)
    await db_session.flush()

    resultado = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )

    filas = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == uuid.UUID(resultado["asiento_id"])
            )
        )
    ).all()
    codigos = sorted(f.cuenta for f in filas)
    assert codigos == ["1110", "2100"]
    assert all(codigo[0] in "123" for codigo in codigos)
    total_debe = sum(f.debe for f in filas)
    total_haber = sum(f.haber for f in filas)
    assert total_debe == total_haber
    assert total_debe > Decimal(0)
    assert resultado["importe_total_debe"] == "5000.0000"
    assert resultado["total_lineas"] == 2


async def test_sin_cuentas_patrimoniales_es_error(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _cerrar_con_saldos(
        db_session,
        10,
        2026,
        [
            ("5720", "900.0000", "0"),
            ("7000", "0", "900.0000"),
        ],
    )
    await _definir_destino(db_session, 10, 2027)
    await db_session.flush()

    try:
        await generar_asiento_apertura(
            db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
        )
        raise AssertionError("debería fallar")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "cuentas_patrimoniales_vacias"


async def test_asiento_en_diario_es_inmutable(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _cerrar_con_saldos(
        db_session,
        10,
        2026,
        [
            ("1110", "0", "2000.0000"),
            ("2100", "2000.0000", "0"),
        ],
    )
    await _definir_destino(db_session, 10, 2027)
    await db_session.flush()

    resultado = await generar_asiento_apertura(
        db_session, empresa_id=10, ejercicio_destino=2027, actor="ana"
    )

    asiento = await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.id == uuid.UUID(resultado["asiento_id"]),
        )
    )
    assert asiento.estado == JournalEntryEstado.POSTED
    assert asiento.tipo == JournalEntryTipo.OPENING
    assert asiento.ejercicio == 2027
    assert asiento.numero_asiento == 1