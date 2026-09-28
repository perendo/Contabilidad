"""Tests SPEC-004 US2 (T020): saldo acumulado exacto del mayor."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.journal.entry_service import asentar, crear_borrador
from services.reports.ledger import LedgerError, ledger


async def _pgc(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    db.add(
        Company(company_id=tenant_id, nif=f"T{tenant_id:08d}", razon_social="E SL")
    )
    await db.flush()
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


async def _asentar(
    db: AsyncSession, tenant_id: int, cuentas: dict[str, int],
    fecha: date, debe_cta: str, haber_cta: str, importe: str,
):
    borrador = await crear_borrador(
        db, empresa_id=tenant_id, fecha=fecha, concepto="M",
        lineas=[
            {"account_id": cuentas[debe_cta], "debit": importe, "credit": "0"},
            {"account_id": cuentas[haber_cta], "debit": "0", "credit": importe},
        ],
        actor="test",
    )
    return await asentar(db, empresa_id=tenant_id, entry_id=borrador.id, actor="test")


async def test_saldo_acumulado_mixto_exacto(db_session: AsyncSession) -> None:
    cuentas = await _pgc(db_session, 10)
    await _asentar(db_session, 10, cuentas, date(2026, 1, 10), "4300", "5720", "100.0000")
    await _asentar(db_session, 10, cuentas, date(2026, 2, 10), "5720", "4300", "30.0000")
    await _asentar(db_session, 10, cuentas, date(2026, 3, 10), "4300", "5720", "10.0000")
    mayor = await ledger(db_session, empresa_id=10, account_id=cuentas["4300"])
    assert [m["saldo_acumulado"] for m in mayor["movimientos"]] == [
        "100.0000", "70.0000", "80.0000",
    ]
    assert mayor["saldo_final"] == "80.0000"
    assert mayor["cuenta"]["code"] == "4300"


async def test_mayor_vacio_200_sin_movimientos(db_session: AsyncSession) -> None:
    cuentas = await _pgc(db_session, 10)
    mayor = await ledger(db_session, empresa_id=10, account_id=cuentas["4300"])
    assert mayor["movimientos"] == []
    assert mayor["saldo_final"] == "0.0000"


async def test_rango_filtra_movimientos(db_session: AsyncSession) -> None:
    cuentas = await _pgc(db_session, 10)
    await _asentar(db_session, 10, cuentas, date(2026, 1, 10), "4300", "5720", "100.0000")
    await _asentar(db_session, 10, cuentas, date(2026, 6, 10), "4300", "5720", "50.0000")
    mayor = await ledger(
        db_session, empresa_id=10, account_id=cuentas["4300"],
        date_from=date(2026, 5, 1), date_to=date(2026, 12, 31),
    )
    assert len(mayor["movimientos"]) == 1
    assert mayor["saldo_final"] == "50.0000"


async def test_rango_invertido_422(db_session: AsyncSession) -> None:
    cuentas = await _pgc(db_session, 10)
    with pytest.raises(LedgerError) as exc:
        await ledger(
            db_session, empresa_id=10, account_id=cuentas["4300"],
            date_from=date(2026, 12, 31), date_to=date(2026, 1, 1),
        )
    assert exc.value.code == "rango_invertido"
