"""Resolucion historica del catalogo (SPEC-025 T013, FR-003/SC-001).

Una fecha resuelve con la version cuya vigencia la cubre; sin cobertura se
usa la version mas antigua con ``resolucion=fallback`` auditado. Ninguna
version se migra retroactivamente.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from models.audit.audit_log import AuditLog
from models.catalog.catalogo_version import EstadoVersion
from services.catalog._comun import crear_version_completa
from services.catalog.errores import CatalogoError
from services.catalog.resolucion_historica import resolver_version
from tests.conftest import sembrar_empresa_pgc


async def _vigente(db, codigo: str, inicio: date, fin: date | None):
    version = await crear_version_completa(
        db,
        empresa_id=10,
        codigo=codigo,
        fecha_inicio=inicio,
        fecha_fin=fin,
        operaciones=[],
        mapeo_explicito=[],
        actor="test",
    )
    version.estado = EstadoVersion.vigente
    await db.flush()
    return version


async def test_resuelve_por_fecha_de_cobertura(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _vigente(db_session, "CAT-2025", date(2025, 1, 1), date(2025, 12, 31))
    await _vigente(db_session, "CAT-2026", date(2026, 1, 1), date(2026, 12, 31))

    r_2025 = await resolver_version(
        db_session, empresa_id=10, fecha=date(2025, 11, 15)
    )
    assert r_2025["codigo"] == "CAT-2025"
    assert r_2025["resolucion"] == "vigente"

    r_2026 = await resolver_version(db_session, empresa_id=10, fecha=date(2026, 3, 1))
    assert r_2026["codigo"] == "CAT-2026"
    assert r_2026["resolucion"] == "vigente"


async def test_fallback_trazable(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _vigente(db_session, "CAT-2025", date(2025, 1, 1), date(2025, 12, 31))
    await _vigente(db_session, "CAT-2027", date(2027, 1, 1), date(2027, 12, 31))

    r = await resolver_version(db_session, empresa_id=10, fecha=date(2028, 5, 1))
    assert r["resolucion"] == "fallback"
    assert r["codigo"] == "CAT-2025"

    auditoria = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.operacion == "RESOLUCION_FALLBACK")
        )
    ).all()
    assert len(auditoria) == 1
    assert auditoria[0].empresa_id == 10
    assert "2028-05-01" in (auditoria[0].payload or "")


async def test_sin_versiones_404(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    with pytest.raises(CatalogoError) as exc:
        await resolver_version(db_session, empresa_id=10, fecha=date(2025, 6, 1))
    assert exc.value.code == "version_no_encontrada"
    assert exc.value.status_code == 404


async def test_sin_migracion_retroactiva(db_session):
    """La version 2026 no altera la resolucion de fechas de 2025."""
    await sembrar_empresa_pgc(db_session, 10)
    v2025 = await _vigente(
        db_session, "CAT-2025", date(2025, 1, 1), date(2025, 12, 31)
    )
    antes = (v2025.fecha_inicio, v2025.fecha_fin, v2025.estado)
    await _vigente(db_session, "CAT-2026", date(2026, 1, 1), None)

    r = await resolver_version(db_session, empresa_id=10, fecha=date(2025, 6, 1))
    assert r["version_id"] == str(v2025.id)
    assert (v2025.fecha_inicio, v2025.fecha_fin, v2025.estado) == antes
