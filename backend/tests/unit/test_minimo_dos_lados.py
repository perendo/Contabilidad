"""T105: Test mínimo una línea por lado (SPEC-006 US2).

Exactamente 1 línea al Debe y 1 al Haber es válido (caso clásico); 0 líneas
en un lado se rechaza con `lado_vacio`.
"""

from __future__ import annotations

from datetime import date

import pytest

from services.journal.motor import crear_asiento_multilinea
from services.journal.validador_multilinea import MultilineaError
from tests.conftest import sembrar_empresa_pgc


async def test_una_linea_por_lado_es_valido(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    entrada = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="Minimo",
        lineas=[
            {"cuenta": "6000", "debe": "1.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "1.0000"},
        ],
    )
    await db_session.flush()
    assert entrada.estado.value == "POSTED"


async def test_cero_en_un_lado_rechazado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    with pytest.raises(MultilineaError) as exc:
        await crear_asiento_multilinea(
            db_session, empresa_id=10, fecha=date(2026, 9, 1),
            concepto="Sin haber",
            lineas=[{"cuenta": "6000", "debe": "1.0000", "haber": "0.0000"}],
        )
    assert exc.value.code == "lado_vacio"