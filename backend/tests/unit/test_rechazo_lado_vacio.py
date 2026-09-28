"""T008: Test rechazo lado vacío (SPEC-006 US1)."""

from __future__ import annotations

from datetime import date

import pytest

from services.journal.motor import crear_asiento_multilinea
from services.journal.validador_multilinea import MultilineaError
from tests.conftest import sembrar_empresa_pgc


async def test_sin_haber_se_rechaza(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    solo_debe = [
        {"cuenta": "6000", "debe": "100.0000", "haber": "0.0000"},
        {"cuenta": "6210", "debe": "50.0000", "haber": "0.0000"},
    ]
    with pytest.raises(MultilineaError) as exc:
        await crear_asiento_multilinea(
            db_session,
            empresa_id=10,
            fecha=date(2026, 9, 1),
            concepto="Sin haber",
            lineas=solo_debe,
        )
    assert exc.value.code == "lado_vacio"
    assert "HABER" in str(exc.value)


async def test_sin_debe_se_rechaza(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    solo_haber = [
        {"cuenta": "4000", "debe": "0.0000", "haber": "100.0000"},
        {"cuenta": "4100", "debe": "0.0000", "haber": "50.0000"},
    ]
    with pytest.raises(MultilineaError) as exc:
        await crear_asiento_multilinea(
            db_session,
            empresa_id=10,
            fecha=date(2026, 9, 1),
            concepto="Sin debe",
            lineas=solo_haber,
        )
    assert exc.value.code == "lado_vacio"
    assert "DEBE" in str(exc.value)