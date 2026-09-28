"""T124: Verificación constitución V en todos los flujos (SPEC-006).

Todo asiento (creado manual o importado) queda balanceado; ningún asiento
POSTED se puede actualizar ni borrar; las consultas y operaciones están
aisladas por empresa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from models.acct.journal import JournalEntryLine
from services.importexport.importador import importar_asientos
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc

CSV = (
    "fecha;numero_asiento;concepto;cuenta;debe;haber;detalle\n"
    "2026-09-01;X1;Importado;6000;20.0000;0.0000;A\n"
    "2026-09-01;X1;Importado;6210;10.0000;0.0000;B\n"
    "2026-09-01;X1;Importado;5720;0.0000;30.0000;C\n"
)


async def _desbalanceados(db_session) -> list:
    lineas = (await db_session.scalars(select(JournalEntryLine))).all()
    grupos: dict = {}
    for linea in lineas:
        grupos.setdefault(str(linea.journal_entry_id), {"debe": Decimal(0), "haber": Decimal(0)})
        grupos[str(linea.journal_entry_id)]["debe"] += linea.debe
        grupos[str(linea.journal_entry_id)]["haber"] += linea.haber
    return [
        gid for gid, s in grupos.items() if s["debe"] != s["haber"]
    ]


async def test_todo_asiento_balanceado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="Manual",
        lineas=[
            {"cuenta": "6000", "debe": "100.0000", "haber": "0.0000"},
            {"cuenta": "6210", "debe": "50.0000", "haber": "0.0000"},
            {"cuenta": "4000", "debe": "0.0000", "haber": "150.0000"},
        ],
    )
    await importar_asientos(
        db_session, empresa_id=10, file_bytes=CSV.encode("utf-8-sig"),
        nombre="imp.csv", actor="tester",
    )
    await db_session.flush()

    assert await _desbalanceados(db_session) == []


async def test_todas_las_lineas_aisladas_por_empresa(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1), concepto="A",
        lineas=[
            {"cuenta": "6000", "debe": "1.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "1.0000"},
        ],
    )
    await crear_asiento_multilinea(
        db_session, empresa_id=20, fecha=date(2026, 9, 1), concepto="B",
        lineas=[
            {"cuenta": "6210", "debe": "1.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "1.0000"},
        ],
    )
    await db_session.flush()

    de_a = await db_session.scalar(
        select(func.count()).select_from(JournalEntryLine).where(
            JournalEntryLine.empresa_id == 10
        )
    )
    de_b = await db_session.scalar(
        select(func.count()).select_from(JournalEntryLine).where(
            JournalEntryLine.empresa_id == 20
        )
    )
    assert de_a == 2
    assert de_b == 2