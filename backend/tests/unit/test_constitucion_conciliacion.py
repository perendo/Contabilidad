"""Tests SPEC-013 Polish (T049): constitución V en conciliación."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado
from services.journal.entry_service import asentar, crear_borrador
from services.reconciliation.conciliacion import abrir_conciliacion
from services.reconciliation.importacion import importar_extracto
from services.reconciliation.saldos import saldo_libros
from tests.conftest import sembrar_empresa_pgc

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


async def test_saldos_en_decimal_y_posted_intacto(db_session: AsyncSession) -> None:
    await sembrar_empresa_pgc(db_session, 10)
    cuentas = {
        c.code: c.id
        for c in (
            await db_session.scalars(
                select(AccountPlan).where(
                    AccountPlan.tenant_id == 10,
                    AccountPlan.code.in_(["5720", "4000"]),
                )
            )
        ).all()
    }
    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 9, 12), concepto="Pago",
        lineas=[
            {"account_id": cuentas["5720"], "debit": "500.0000", "credit": "0"},
            {"account_id": cuentas["4000"], "debit": "0", "credit": "500.0000"},
        ],
        actor="t",
    )
    asiento = await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="t")
    extracto = await importar_extracto(
        db_session, empresa_id=10,
        file_bytes=(FIXTURES / "extracto_43_19_valido.txt").read_bytes(),
        nombre_fichero="v.txt", actor="t",
    )
    conc = await abrir_conciliacion(
        db_session, empresa_id=10, cuenta_id=cuentas["5720"],
        fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30),
        extracto_id=extracto.id, actor="t",
    )
    saldo = await saldo_libros(db_session, 10, conc)
    assert isinstance(saldo, Decimal)
    assert not isinstance(saldo, float)
    # El asiento POSTED no se modifica al conciliar
    original = await db_session.get(JournalEntry, asiento.id)
    assert original is not None
    assert original.estado == JournalEntryEstado.POSTED
    assert original.numero_asiento == asiento.numero_asiento


async def test_extracto_defecto_no_visible_en_otra_empresa(db_session: AsyncSession) -> None:
    from models.treasury.extracto_bancario import ExtractoBancario

    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    extracto = await importar_extracto(
        db_session, empresa_id=10,
        file_bytes=(FIXTURES / "extracto_43_19_valido.txt").read_bytes(),
        nombre_fichero="v.txt", actor="t",
    )
    assert await db_session.scalar(
        select(ExtractoBancario).where(
            ExtractoBancario.empresa_id == 20, ExtractoBancario.id == extracto.id
        )
    ) is None
