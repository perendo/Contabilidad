"""Activacion condicionada a mapeos completos (SPEC-025 T025, FR-004/FR-006).

``activar_version`` rechaza 422 ``mapeo_incompleto`` cuando una cuenta
suprimida con saldo distinto de cero no tiene destino; completar el mapeo a
nivel servicio (decision de diseno) habilita el salto ``borrador -> vigente``.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from models.audit.audit_log import AuditLog
from models.catalog.catalogo_version import EstadoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta
from services.catalog.errores import CatalogoError
from services.catalog.importacion_catalogo import importar_catalogo, parsear_csv
from services.catalog.registro_version import activar_version
from tests.unit.catalogo_support import plan_ids, postear, sembrar_base

CSV_BAJA = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "baja,4300,Clientes,,\n"
)


async def _importar_baja(db) -> str:
    resultado = await importar_catalogo(
        db,
        empresa_id=10,
        codigo_version="NORMA-2026",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        operaciones=parsear_csv(CSV_BAJA),
        mapeo=[],
        actor="test",
    )
    return resultado["version_id"]


async def test_activar_sin_saldos(db_session):
    await sembrar_base(db_session)
    version_id = await _importar_baja(db_session)

    resultado = await activar_version(
        db_session, empresa_id=10, version_id=version_id, actor="admin"
    )

    assert resultado["estado"] == EstadoVersion.vigente.value
    assert resultado["pendientes"] == []
    assert resultado["n_mapeos"] > 0

    auditoria = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.operacion == "ACTIVAR_VERSION")
        )
    ).all()
    assert len(auditoria) == 1
    assert auditoria[0].empresa_id == 10
    assert auditoria[0].entidad == "catalogo_version"
    assert auditoria[0].entidad_id == version_id


async def test_activar_bloqueado_por_saldo(db_session):
    await sembrar_base(db_session)
    ids = await plan_ids(db_session)
    await postear(
        db_session,
        10,
        date(2025, 6, 30),
        [
            {"account_id": ids["4300"], "debit": "250.0000", "credit": "0"},
            {"account_id": ids["1110"], "debit": "0", "credit": "250.0000"},
        ],
    )
    version_id = await _importar_baja(db_session)

    with pytest.raises(CatalogoError) as exc:
        await activar_version(
            db_session, empresa_id=10, version_id=version_id, actor="admin"
        )
    assert exc.value.code == "mapeo_incompleto"
    assert exc.value.status_code == 422
    assert exc.value.extra["pendientes"] == [
        {"codigo": "4300", "motivo": "saldo_no_cero"}
    ]

    auditoria = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.operacion == "ACTIVAR_VERSION")
        )
    ).all()
    assert auditoria == []


async def test_resolucion_de_pendiente_permite_activar(db_session):
    await sembrar_base(db_session)
    ids = await plan_ids(db_session)
    await postear(
        db_session,
        10,
        date(2025, 6, 30),
        [
            {"account_id": ids["4300"], "debit": "250.0000", "credit": "0"},
            {"account_id": ids["1110"], "debit": "0", "credit": "250.0000"},
        ],
    )
    version_id = await _importar_baja(db_session)

    mapeo = (
        await db_session.scalars(
            select(MapeoCuenta).where(
                MapeoCuenta.empresa_id == 10,
                MapeoCuenta.version_destino_id == uuid.UUID(version_id),
                MapeoCuenta.cuenta_destino_id.is_(None),
            )
        )
    ).first()
    assert mapeo is not None

    from models.catalog.catalogo_cuenta import CatalogoCuenta

    destino = (
        await db_session.scalars(
            select(CatalogoCuenta).where(
                CatalogoCuenta.empresa_id == 10,
                CatalogoCuenta.version_id == uuid.UUID(version_id),
                CatalogoCuenta.codigo_version == "4100",
            )
        )
    ).first()
    assert destino is not None
    mapeo.cuenta_destino_id = destino.id
    await db_session.flush()

    resultado = await activar_version(
        db_session, empresa_id=10, version_id=version_id, actor="admin"
    )
    assert resultado["estado"] == EstadoVersion.vigente.value
    assert resultado["pendientes"] == []


async def test_activar_idempotente(db_session):
    await sembrar_base(db_session)
    version_id = await _importar_baja(db_session)
    primera = await activar_version(
        db_session, empresa_id=10, version_id=version_id, actor="admin"
    )
    segunda = await activar_version(
        db_session, empresa_id=10, version_id=version_id, actor="admin"
    )
    assert primera["estado"] == "vigente"
    assert segunda["estado"] == "vigente"
    assert segunda["n_mapeos"] == primera["n_mapeos"]


async def test_activar_no_encontrada(db_session):
    await sembrar_base(db_session)
    with pytest.raises(CatalogoError) as exc:
        await activar_version(
            db_session,
            empresa_id=10,
            version_id=str(uuid.uuid4()),
            actor="admin",
        )
    assert exc.value.code == "version_no_encontrada"
    assert exc.value.status_code == 404


async def test_activar_anulada_409(db_session):
    await sembrar_base(db_session)
    version_id = await _importar_baja(db_session)
    from services.catalog._comun import obtener_version

    version = await obtener_version(db_session, 10, version_id)
    assert version is not None
    version.estado = EstadoVersion.anulada
    await db_session.flush()

    with pytest.raises(CatalogoError) as exc:
        await activar_version(
            db_session, empresa_id=10, version_id=version_id, actor="admin"
        )
    assert exc.value.code == "version_anulada"
    assert exc.value.status_code == 409


async def test_activar_cross_tenant_404(db_session):
    await sembrar_base(db_session, empresa_id=10)
    await sembrar_base(db_session, empresa_id=20, codigo="BASE-2025-B")
    version_id = await _importar_baja(db_session)

    with pytest.raises(CatalogoError) as exc:
        await activar_version(
            db_session, empresa_id=20, version_id=version_id, actor="admin"
        )
    assert exc.value.code == "version_no_encontrada"
    assert exc.value.status_code == 404
