"""Vigencia sin solapes (SPEC-025 T012, FR-006/SC-004).

Servicio (422 ``solape_vigencia``) y trigger SQLite (IntegrityError) rechazan
solapes por empresa; rangos contiguos a fin de anio se aceptan.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from services.catalog._comun import crear_version_completa
from services.catalog.errores import CatalogoError
from tests.unit.catalogo_support import sembrar_base


async def _crear(
    db, codigo: str, inicio: date, fin: date | None, empresa_id: int = 10
):
    return await crear_version_completa(
        db,
        empresa_id=empresa_id,
        codigo=codigo,
        fecha_inicio=inicio,
        fecha_fin=fin,
        operaciones=[],
        mapeo_explicito=[],
        actor="test",
    )


async def test_solape_servicio_422(db_session):
    await sembrar_base(db_session, vigente=False)
    await _crear(db_session, "V-2026", date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(CatalogoError) as exc:
        await _crear(db_session, "SOLAPA", date(2026, 6, 1), date(2027, 6, 30))
    assert exc.value.code == "solape_vigencia"
    assert exc.value.status_code == 422


async def test_rangos_contiguos_aceptados(db_session):
    await sembrar_base(db_session, vigente=False)
    v1 = await _crear(db_session, "2026", date(2026, 1, 1), date(2026, 12, 31))
    v2 = await _crear(db_session, "2027", date(2027, 1, 1), date(2027, 12, 31))
    assert v1.id != v2.id
    total = [v for v in (v1, v2) if v.estado != EstadoVersion.anulada]
    assert len(total) == 2


async def test_solape_trigger_directo(db_session):
    await sembrar_base(db_session, vigente=False)
    db_session.add(
        CatalogoVersion(
            empresa_id=10,
            numero_version=10,
            codigo="TRIG-1",
            fecha_inicio=date(2030, 1, 1),
            fecha_fin=date(2030, 12, 31),
            estado=EstadoVersion.borrador,
        )
    )
    await db_session.flush()
    db_session.add(
        CatalogoVersion(
            empresa_id=10,
            numero_version=11,
            codigo="TRIG-2",
            fecha_inicio=date(2030, 7, 1),
            fecha_fin=date(2031, 7, 31),
            estado=EstadoVersion.borrador,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_solape_no_cruza_empresas(db_session):
    await sembrar_base(db_session, empresa_id=10, vigente=False)
    await sembrar_base(db_session, empresa_id=20, vigente=False)
    v20 = await _crear(
        db_session, "A-2031", date(2031, 1, 1), date(2031, 12, 31), empresa_id=20
    )
    assert v20.empresa_id == 20
    v10 = await _crear(
        db_session, "B-2031", date(2031, 1, 1), date(2031, 12, 31), empresa_id=10
    )
    assert v10.empresa_id == 10
