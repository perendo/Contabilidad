"""Tests SPEC-005 Polish (T038): constitución V en import/export."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.importexport.exportador import exportar_diario
from services.importexport.importador import importar_asientos
from tests.conftest import sembrar_empresa_pgc

CABECERA = "fecha;numero_asiento;concepto;cuenta;debe;haber\n"


def _csv(*lineas: str) -> bytes:
    return (CABECERA + "\n".join(lineas)).encode("utf-8")


async def test_todo_asiento_importado_cuadra_y_es_posted(db_session: AsyncSession) -> None:
    for cid in (10, 20):
        db_session.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
        await db_session.flush()
        await seed_default_pgc(db_session, cid)
    await importar_asientos(
        db_session, empresa_id=10, nombre="a.csv", actor="t",
        file_bytes=_csv(
            "2026-05-01;1;V;4300;100,00;0",
            "2026-05-01;1;V;5720;0;100,00",
            "2026-05-02;2;V;4300;33,33;0",
            "2026-05-02;2;V;5720;0;33,33",
        ),
    )
    entradas = (await db_session.scalars(select(JournalEntry))).all()
    assert len(entradas) == 2
    for entrada in entradas:
        assert entrada.estado == JournalEntryEstado.POSTED
        lineas = (
            await db_session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == entrada.id
                )
            )
        ).all()
        assert sum((l.debe for l in lineas), Decimal(0)) == sum(
            (l.haber for l in lineas), Decimal(0)
        )
    # Ninguna entrada de otra empresa
    n_b = await db_session.scalar(
        select(func.count(JournalEntry.id)).where(JournalEntry.empresa_id == 20)
    )
    assert n_b == 0


async def test_exportar_solo_posted(db_session: AsyncSession) -> None:
    from datetime import date

    from models.acct.account_plan import AccountPlan
    from services.journal.entry_service import crear_borrador

    await sembrar_empresa_pgc(db_session, 10, nif="T00000010", razon_social="E10 SL")
    await importar_asientos(
        db_session, empresa_id=10, nombre="a.csv", actor="t",
        file_bytes=_csv(
            "2026-05-01;1;Importado;4300;10,00;0",
            "2026-05-01;1;Importado;5720;0;10,00",
        ),
    )
    cuentas = {
        c.code: c.id
        for c in (
            await db_session.scalars(
                select(AccountPlan).where(
                    AccountPlan.tenant_id == 10, AccountPlan.code.in_(["4300", "5720"])
                )
            )
        ).all()
    }
    await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 5, 2), concepto="Borrador",
        lineas=[
            {"account_id": cuentas["4300"], "debit": "5.0000", "credit": "0"},
            {"account_id": cuentas["5720"], "debit": "0", "credit": "5.0000"},
        ],
        actor="t",
    )
    contenido, _, _ = await exportar_diario(
        db_session, empresa_id=10,
        fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 12, 31), formato="CSV",
    )
    texto = contenido.decode("utf-8-sig")
    assert "Importado" in texto
    assert "Borrador" not in texto
