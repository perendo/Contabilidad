"""Correlatividad de numero_version (SPEC-025 T014, constitucion IV).

Secuencia 1, 2, 3 sin saltos por empresa; cada empresa tiene la suya.
"""

from __future__ import annotations

from datetime import date

from services.catalog._comun import crear_version_completa
from tests.conftest import sembrar_empresa_pgc


async def _crear(db, empresa_id: int, codigo: str, inicio: date):
    return await crear_version_completa(
        db,
        empresa_id=empresa_id,
        codigo=codigo,
        fecha_inicio=inicio,
        fecha_fin=date(inicio.year, 12, 31),
        operaciones=[],
        mapeo_explicito=[],
        actor="test",
    )


async def test_tres_versiones_secuencia_sin_saltos(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    v1 = await _crear(db_session, 10, "V1", date(2026, 1, 1))
    v2 = await _crear(db_session, 10, "V2", date(2027, 1, 1))
    v3 = await _crear(db_session, 10, "V3", date(2028, 1, 1))
    assert [v1.numero_version, v2.numero_version, v3.numero_version] == [1, 2, 3]


async def test_secuencia_independiente_por_empresa(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    a1 = await _crear(db_session, 10, "A1", date(2026, 1, 1))
    a2 = await _crear(db_session, 10, "A2", date(2027, 1, 1))
    b1 = await _crear(db_session, 20, "B1", date(2026, 1, 1))
    assert a1.numero_version == 1
    assert a2.numero_version == 2
    assert b1.numero_version == 1
