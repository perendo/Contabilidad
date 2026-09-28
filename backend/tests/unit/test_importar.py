"""Tests SPEC-005 US2 (T020-T023): importación atómica, correlativa, parcial y auditada."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.audit.audit_log import AuditLog
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.importexport.importador import importar_asientos

CABECERA = "fecha;numero_asiento;concepto;cuenta;debe;haber\n"


def _csv(*lineas: str) -> bytes:
    return (CABECERA + "\n".join(lineas)).encode("utf-8")


async def _empresa(db: AsyncSession, cid: int = 10) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()
    await seed_default_pgc(db, cid)


async def _importar(db: AsyncSession, datos: bytes, cid: int = 10) -> dict:
    return await importar_asientos(
        db, empresa_id=cid, file_bytes=datos, nombre="a.csv", actor="tester"
    )


async def test_importa_validos_con_cabecera_y_lineas(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    resultado = await _importar(
        db_session,
        _csv(
            "2026-05-01;1;Venta;4300;100,00;0",
            "2026-05-01;1;Venta;5720;0;100,00",
            "2026-05-02;2;Compra;6000;50,00;0",
            "2026-05-02;2;Compra;5720;0;50,00",
            "2026-05-03;3;Otra;4300;25,00;0",
            "2026-05-03;3;Otra;5720;0;25,00",
        ),
    )
    assert resultado["asientos_importados"] == 3
    assert resultado["asientos_omitidos"] == 0
    for entrada in (await db_session.scalars(select(JournalEntry))).all():
        assert entrada.estado == JournalEntryEstado.POSTED
        lineas = (
            await db_session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == entrada.id
                )
            )
        ).all()
        debe = sum((l.debe for l in lineas), Decimal(0))
        haber = sum((l.haber for l in lineas), Decimal(0))
        assert debe == haber


async def test_numeracion_correlativa(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    lineas = []
    for n in range(1, 6):
        lineas += [f"2026-05-0{n};{n};V;4300;10,00;0", f"2026-05-0{n};{n};V;5720;0;10,00"]
    resultado = await _importar(db_session, _csv(*lineas))
    assert resultado["primer_numero_asiento"] == 1
    assert resultado["ultimo_numero_asiento"] == 5
    numeros = sorted(
        e.numero_asiento
        for e in (await db_session.scalars(select(JournalEntry))).all()
    )
    assert numeros == [1, 2, 3, 4, 5]


async def test_omision_parcial(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    resultado = await _importar(
        db_session,
        _csv(
            "2026-05-01;1;V;4300;100,00;0",
            "2026-05-01;1;V;5720;0;100,00",
            "2026-05-02;2;Desbalanceado;4300;10,00;0",
            "2026-05-02;2;Desbalanceado;5720;0;5,00",
        ),
    )
    assert resultado["asientos_importados"] == 1
    assert resultado["asientos_omitidos"] == 1
    n = await db_session.scalar(select(func.count(JournalEntry.id)))
    assert n == 1


async def test_auditoria_importacion(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    await _importar(
        db_session,
        _csv(
            "2026-05-01;1;V;4300;100,00;0",
            "2026-05-01;1;V;5720;0;100,00",
        ),
    )
    registros = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.operacion == "IMPORT_ASIENTOS")
        )
    ).all()
    assert len(registros) == 1
    assert registros[0].usuario == "tester"
