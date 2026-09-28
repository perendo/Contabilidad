"""Tests SPEC-004 US1 (T012/T013): cuadre y agregación por nivel del balance."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.journal.entry_service import asentar, crear_borrador
from services.reports.trial_balance import BalanceError, trial_balance


async def _empresa(db: AsyncSession, company_id: int) -> None:
    db.add(
        Company(
            company_id=company_id,
            nif=f"T{company_id:08d}",
            razon_social=f"Empresa {company_id} SL",
        )
    )
    await db.flush()


async def _cuenta(
    db: AsyncSession, tenant_id: int, codigo: str, nombre: str, padre: int | None
) -> int:
    cuenta = AccountPlan(
        tenant_id=tenant_id, code=codigo, name=nombre,
        parent_id=padre, level=len(codigo), is_active=True,
        is_selectable=len(codigo) >= 4,
    )
    db.add(cuenta)
    await db.flush()
    return cuenta.id


async def _pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    ids: dict[str, int] = {}
    for codigo in ("4", "43", "430", "4300", "5", "57", "572", "5720"):
        ids[codigo] = await _cuenta(
            db, tenant_id, codigo, f"C-{codigo}",
            ids.get(codigo[:-1]) if len(codigo) > 1 else None,
        )
    return ids


async def _asiento(
    db: AsyncSession, tenant_id: int, cuentas: dict[str, int], fecha: date, importe: str
):
    borrador = await crear_borrador(
        db,
        empresa_id=tenant_id,
        fecha=fecha,
        concepto="Venta",
        lineas=[
            {"account_id": cuentas["4300"], "debit": importe, "credit": "0"},
            {"account_id": cuentas["5720"], "debit": "0", "credit": importe},
        ],
        actor="test",
    )
    return await asentar(db, empresa_id=tenant_id, entry_id=borrador.id, actor="test")


async def test_cuadre_en_multiples_rangos_y_niveles(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    cuentas = await _pgc(db_session, 10)
    await _asiento(db_session, 10, cuentas, date(2026, 1, 15), "100.0000")
    await _asiento(db_session, 10, cuentas, date(2026, 6, 30), "55.5000")
    for rango in [
        (date(2026, 1, 1), date(2026, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 7, 1), date(2026, 12, 31)),
    ]:
        for nivel in (1, 2, 3, 4):
            balance = await trial_balance(
                db_session, empresa_id=10,
                date_from=rango[0], date_to=rango[1], level=nivel,
            )
            assert balance["cuadra"] is True
            assert Decimal(balance["total_debe"]) == Decimal(balance["total_haber"])


async def test_borradores_no_computan(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    cuentas = await _pgc(db_session, 10)
    await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 2, 1), concepto="Borrador",
        lineas=[
            {"account_id": cuentas["4300"], "debit": "999.0000", "credit": "0"},
            {"account_id": cuentas["5720"], "debit": "0", "credit": "999.0000"},
        ],
        actor="test",
    )
    balance = await trial_balance(
        db_session, empresa_id=10,
        date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), level=4,
    )
    assert balance["total_debe"] == "0.0000"
    assert balance["items"] == []


async def test_rango_invertido_422(db_session: AsyncSession) -> None:
    with pytest.raises(BalanceError) as exc:
        await trial_balance(
            db_session, empresa_id=10,
            date_from=date(2026, 12, 31), date_to=date(2026, 1, 1), level=4,
        )
    assert exc.value.code == "rango_invertido"
