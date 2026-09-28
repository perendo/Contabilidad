"""T007: Test rechazo desbalanceo (SPEC-006 US1).

Verifica que un asiento 2:1 desbalanceado se rechaza con `desbalanceo` y que
NO se persiste ni la cabecera ni ninguna línea (transacción indivisible).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine
from services.journal.motor import crear_asiento_multilinea
from services.journal.validador_multilinea import MultilineaError
from tests.conftest import sembrar_empresa_pgc


async def test_rechazo_desbalanceo_no_escribe_nada(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    desbalanceado = [
        {"cuenta": "6000", "debe": "500.0000", "haber": "0.0000"},
        {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000"},
    ]
    with pytest.raises(MultilineaError) as exc:
        await crear_asiento_multilinea(
            db_session,
            empresa_id=10,
            fecha=date(2026, 9, 1),
            concepto="Desbalanceado",
            lineas=desbalanceado,
        )
    assert exc.value.code == "desbalanceo"
    await db_session.flush()

    n_cabeceras = await db_session.scalar(select(func.count()).select_from(JournalEntry))
    n_lineas = await db_session.scalar(select(func.count()).select_from(JournalEntryLine))
    assert n_cabeceras == 0
    assert n_lineas == 0