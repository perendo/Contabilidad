"""Tests SPEC-004 US3 (T028/T029/T030): doble cierre, borradores y balance."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.iam.company import Company
from services.closing.close_year import CierreError, cerrar_ejercicio
from services.journal.entry_service import asentar, crear_borrador


async def _cuenta(
    db: AsyncSession, tenant_id: int, codigo: str, padre: int | None
) -> int:
    cuenta = AccountPlan(
        tenant_id=tenant_id, code=codigo, name=f"C-{codigo}",
        parent_id=padre, level=len(codigo), is_active=True, is_selectable=True,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta.id


async def _pgc_cierre(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    db.add(
        Company(company_id=tenant_id, nif=f"T{tenant_id:08d}", razon_social="E SL")
    )
    await db.flush()
    ids: dict[str, int] = {}
    for codigo in ("1", "12", "129", "5", "57", "572", "5720", "6", "60", "600", "6000", "7", "70", "700", "7000"):
        ids[codigo] = await _cuenta(
            db, tenant_id, codigo,
            ids.get(codigo[:-1]) if len(codigo) > 1 else None,
        )
    db.add(
        FiscalYear(
            empresa_id=tenant_id, year=2026,
            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31),
        )
    )
    await db.flush()
    return ids


async def _gasto_ingreso(db: AsyncSession, tenant_id: int, c: dict[str, int]):
    for debe, haber, importe in (("6000", "5720", "200.0000"), ("5720", "7000", "500.0000")):
        borrador = await crear_borrador(
            db, empresa_id=tenant_id, fecha=date(2026, 5, 1), concepto="Op",
            lineas=[
                {"account_id": c[debe], "debit": importe, "credit": "0"},
                {"account_id": c[haber], "debit": "0", "credit": importe},
            ],
            actor="test",
        )
        await asentar(db, empresa_id=tenant_id, entry_id=borrador.id, actor="test")


async def test_cierre_balanceado_posted_inmutable(db_session: AsyncSession) -> None:
    c = await _pgc_cierre(db_session, 10)
    await _gasto_ingreso(db_session, 10, c)
    resultado = await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    assert resultado["is_closed"] is True
    for clave in ("regularizacion_entry_id", "cierre_entry_id"):
        assert resultado[clave] is not None
        asiento = await db_session.get(JournalEntry, UUID(resultado[clave]))
        assert asiento.estado == JournalEntryEstado.POSTED
        assert asiento.tipo == JournalEntryTipo.ADJUSTMENT
    fy = await db_session.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == 10, FiscalYear.year == 2026)
    )
    assert fy is not None and fy.is_closed and fy.closed_at is not None


async def test_ejercicio_vacio_cierra_sin_asientos(db_session: AsyncSession) -> None:
    await _pgc_cierre(db_session, 10)
    resultado = await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    assert resultado["is_closed"] is True
    assert resultado["regularizacion_entry_id"] is None
    assert resultado["cierre_entry_id"] is None


async def test_ejercicio_inexistente_404(db_session: AsyncSession) -> None:
    await _pgc_cierre(db_session, 10)
    with pytest.raises(CierreError) as exc:
        await cerrar_ejercicio(db_session, empresa_id=10, year=2027, actor="test")
    assert exc.value.code == "ejercicio_no_encontrado"


async def test_regularizacion_salda_6_7_contra_129(db_session: AsyncSession) -> None:
    from models.acct.journal import JournalEntryLine

    c = await _pgc_cierre(db_session, 10)
    await _gasto_ingreso(db_session, 10, c)
    resultado = await cerrar_ejercicio(db_session, empresa_id=10, year=2026, actor="test")
    reg_id = UUID(resultado["regularizacion_entry_id"])
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == reg_id,
                JournalEntryLine.empresa_id == 10,
            )
        )
    ).all()
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    assert debe == haber == Decimal("700.0000")
    por_cuenta: dict[str, list] = {}
    for l in lineas:
        por_cuenta.setdefault(l.cuenta, [Decimal(0), Decimal(0)])
        por_cuenta[l.cuenta][0] += l.debe
        por_cuenta[l.cuenta][1] += l.haber
    assert por_cuenta["6000"] == [Decimal(0), Decimal("200.0000")]
    assert por_cuenta["7000"] == [Decimal("500.0000"), Decimal(0)]
    assert por_cuenta["1290"] == [Decimal("200.0000"), Decimal("500.0000")]
