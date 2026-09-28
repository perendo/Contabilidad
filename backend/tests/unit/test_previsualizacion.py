"""Tests SPEC-005 US1 (T011/T012): previsualización dry-run sin escritura."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.importexport.importador import previsualizar_importacion

CABECERA = "fecha;numero_asiento;concepto;cuenta;debe;haber\n"


def _csv(*lineas: str) -> bytes:
    return (CABECERA + "\n".join(lineas)).encode("utf-8")


async def _empresa(db: AsyncSession, cid: int = 10) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()
    await seed_default_pgc(db, cid)


async def test_dryrun_no_escribe_y_clasifica(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    datos = _csv(
        "2026-05-01;1;Venta;4300;100,00;0",
        "2026-05-01;1;Venta;5720;0;100,00",
        "2026-05-02;2;Compra;6000;50,00;0",
        "2026-05-02;2;Compra;5720;0;50,00",
        "2026-05-03;3;Desbalanceado;4300;10,00;0",
        "2026-05-03;3;Desbalanceado;5720;0;5,00",
    )
    resultado = await previsualizar_importacion(
        db_session, empresa_id=10, file_bytes=datos, nombre="a.csv"
    )
    assert resultado["total_asientos"] == 3
    assert resultado["asientos_validos"] == 2
    assert resultado["asientos_con_error"] == 1
    assert resultado["errores"][0]["tipo_error"] == "desbalanceo"
    n = await db_session.scalar(select(func.count(JournalEntry.id)))
    assert n == 0


async def test_cuenta_inexistente_y_no_apuntable(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    datos = _csv(
        "2026-05-01;1;V;9999;10,00;0",
        "2026-05-01;1;V;5720;0;10,00",
        "2026-05-02;2;V;430;10,00;0",
        "2026-05-02;2;V;5720;0;10,00",
    )
    resultado = await previsualizar_importacion(
        db_session, empresa_id=10, file_bytes=datos, nombre="a.csv"
    )
    tipos = {e["tipo_error"] for e in resultado["errores"]}
    assert "cuenta_no_encontrada" in tipos
    assert "cuenta_no_apuntable" in tipos


async def test_ejercicio_cerrado(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    db_session.add(
        FiscalYear(
            empresa_id=10, year=2026, date_start=date(2026, 1, 1),
            date_end=date(2026, 12, 31), is_closed=True,
        )
    )
    await db_session.flush()
    datos = _csv(
        "2026-05-01;1;V;4300;10,00;0",
        "2026-05-01;1;V;5720;0;10,00",
    )
    resultado = await previsualizar_importacion(
        db_session, empresa_id=10, file_bytes=datos, nombre="a.csv"
    )
    assert resultado["asientos_con_error"] == 1
    assert resultado["errores"][0]["tipo_error"] == "ejercicio_cerrado"
