"""Constitucion del catalogo (SPEC-025 T042).

III: ninguna version/cuenta/mapping cruza empresas (404). IV: los
``numero_version`` correlativos no se mezclan. I: la reclasificacion exige
Debe == Haber. Regla fiscal: los importes son strings de 4 decimales /
``Decimal`` (nunca ``float``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.audit.audit_log import AuditLog
from models.catalog.catalogo_version import CatalogoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta
from services.catalog._comun import importe_str, obtener_version, saldos_ejercicio
from services.catalog.errores import CatalogoError
from services.catalog.reclasificacion_saldos import preview_reclasificacion
from services.catalog.registro_version import (
    activar_version,
    detalle_version,
    listar_versiones,
    registrar_version,
)
from services.catalog.resolucion_historica import resolver_version
from tests.unit.catalogo_support import (
    objetivo_2026,
    preparar_trasvase,
    sembrar_base,
)


async def test_version_cross_tenant_no_visible(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)

    assert await obtener_version(db_session, 20, objetivo) is None

    with pytest.raises(CatalogoError) as exc:
        await detalle_version(db_session, empresa_id=20, version_id=objetivo)
    assert exc.value.code == "version_no_encontrada"
    assert exc.value.status_code == 404


async def test_activar_cross_tenant(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    with pytest.raises(CatalogoError) as exc:
        await activar_version(db_session, empresa_id=20, version_id=objetivo, actor="x")
    assert exc.value.code == "version_no_encontrada"


async def test_preview_y_resolucion_cross_tenant(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    with pytest.raises(CatalogoError) as exc:
        await preview_reclasificacion(
            db_session, empresa_id=20, version_id=objetivo, ejercicio=2025
        )
    assert exc.value.code == "version_no_encontrada"

    with pytest.raises(CatalogoError) as exc:
        await resolver_version(db_session, empresa_id=20, fecha=date(2025, 6, 1))
    assert exc.value.code == "version_no_encontrada"
    assert exc.value.status_code == 404


async def test_listado_y_mapeos_no_cruzan_empresas(db_session):
    await sembrar_base(db_session, empresa_id=10)
    await sembrar_base(db_session, empresa_id=20, codigo="BASE-B")
    objetivo = await objetivo_2026(db_session, empresa_id=10)

    listado_20 = await listar_versiones(db_session, empresa_id=20, page_size=50)
    codigos_20 = {v["codigo"] for v in listado_20["items"]}
    assert codigos_20 == {"BASE-B"}
    assert listado_20["total"] == 1

    mapeos_10 = int(
        await db_session.scalar(
            select(func.count())
            .select_from(MapeoCuenta)
            .where(MapeoCuenta.empresa_id == 10)
        )
        or 0
    )
    mapeos_20 = int(
        await db_session.scalar(
            select(func.count())
            .select_from(MapeoCuenta)
            .where(MapeoCuenta.empresa_id == 20)
        )
        or 0
    )
    assert mapeos_10 > 0
    assert mapeos_20 == 0

    versiones_10 = (
        await db_session.scalars(
            select(CatalogoVersion).where(CatalogoVersion.empresa_id == 10)
        )
    ).all()
    assert all(v.empresa_id == 10 for v in versiones_10)
    assert objetivo.id in {v.id for v in versiones_10}


async def test_correlatividad_por_empresa_constitucion_iv(db_session):
    await sembrar_base(db_session, empresa_id=10)
    await sembrar_base(db_session, empresa_id=20, codigo="BASE-B")
    v10 = await registrar_version(
        db_session,
        empresa_id=10,
        codigo="NORMA-A",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        operaciones=[],
        actor="test",
    )
    v20 = await registrar_version(
        db_session,
        empresa_id=20,
        codigo="NORMA-B",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        operaciones=[],
        actor="test",
    )
    assert v10["numero_version"] == 2
    assert v20["numero_version"] == 2

    auditoria = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.operacion == "ALTA_VERSION",
                AuditLog.empresa_id == 10,
            )
        )
    ).all()
    assert len(auditoria) == 1
    assert auditoria[0].entidad_id == v10["id"]


async def test_importes_decimal_cuatro_decimales(db_session):
    assert importe_str(Decimal(12500)) == "12500.0000"
    assert importe_str(Decimal("0.5")) == "0.5000"
    assert isinstance(importe_str(Decimal(1)), str)

    _base, objetivo, _ids = await preparar_trasvase(db_session)
    preview = await preview_reclasificacion(
        db_session, empresa_id=10, version_id=objetivo, ejercicio=2025
    )
    total = preview["total_importe"]
    assert isinstance(total, str)
    assert len(total.split(".")[1]) == 4
    assert not isinstance(preview["items"][0]["importe"], float)

    saldos = await saldos_ejercicio(db_session, 10, 2025)
    assert saldos
    assert all(isinstance(valor, Decimal) for valor in saldos.values())
    assert all(not isinstance(valor, float) for valor in saldos.values())
