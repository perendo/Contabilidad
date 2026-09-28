"""Tests SPEC-004 US1 (T014): asientos de otra empresa jamás entran al balance."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.journal.entry_service import asentar, crear_borrador
from services.reports.trial_balance import trial_balance


async def _pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    ids: dict[str, int] = {}
    for codigo in ("4", "43", "430", "4300", "5", "57", "572", "5720"):
        cuenta = AccountPlan(
            tenant_id=tenant_id, code=codigo, name=f"C-{codigo}",
            parent_id=ids.get(codigo[:-1]) if len(codigo) > 1 else None,
            level=len(codigo), is_active=True, is_selectable=len(codigo) >= 4,
        )
        db.add(cuenta)
        await db.flush()
        ids[codigo] = cuenta.id
    return ids


async def _asentado(db: AsyncSession, tenant_id: int, cuentas: dict[str, int], importe: str):
    borrador = await crear_borrador(
        db, empresa_id=tenant_id, fecha=date(2026, 4, 1), concepto="V",
        lineas=[
            {"account_id": cuentas["4300"], "debit": importe, "credit": "0"},
            {"account_id": cuentas["5720"], "debit": "0", "credit": importe},
        ],
        actor="test",
    )
    return await asentar(db, empresa_id=tenant_id, entry_id=borrador.id, actor="test")


async def test_balance_a_excluye_asientos_de_b(db_session: AsyncSession) -> None:
    for empresa in (10, 20):
        db_session.add(
            Company(
                company_id=empresa,
                nif=f"T{empresa:08d}",
                razon_social=f"Empresa {empresa} SL",
            )
        )
    await db_session.flush()
    cuentas_a = await _pgc(db_session, 10)
    cuentas_b = await _pgc(db_session, 20)
    await _asentado(db_session, 10, cuentas_a, "100.0000")
    await _asentado(db_session, 20, cuentas_b, "9999.0000")
    balance = await trial_balance(
        db_session, empresa_id=10,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), level=4,
    )
    assert balance["cuadra"] is True
    assert Decimal(balance["total_debe"]) == Decimal("100.0000")
