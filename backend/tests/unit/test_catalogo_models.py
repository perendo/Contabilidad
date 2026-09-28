"""Modelos fundacionales del catalogo versionado (SPEC-025 T010).

Verifica a nivel metadata e inserts reales:
- unicidad de (empresa_id, numero_version).
- unicidad de la proyeccion (empresa_id, version_id, account_id).
- FK compuesta con empresa_id a la cabeza (version y account_plan).
- solape de vigencia rechazado por trigger (FR-006/SC-004).
- checks de ReclasificacionSaldo (importe >= 0) y NUMERIC(18,4).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from models.acct.account_plan import AccountPlan
from models.catalog.catalogo_cuenta import CatalogoCuenta, EstadoCuentaVersion
from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta, TipoMovimiento
from models.catalog.reclasificacion_saldo import (
    EstadoReclasificacion,
    ReclasificacionSaldo,
)
from tests.conftest import sembrar_empresa_pgc


def _version(
    *,
    empresa_id: int = 10,
    numero: int = 1,
    codigo: str = "V1",
    inicio: date = date(2026, 1, 1),
    fin: date | None = date(2026, 12, 31),
) -> CatalogoVersion:
    return CatalogoVersion(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        numero_version=numero,
        codigo=codigo,
        fecha_inicio=inicio,
        fecha_fin=fin,
        estado=EstadoVersion.borrador,
    )


async def _plan_4300(db, empresa_id: int = 10) -> int:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "4300"
        )
    )
    assert cuenta is not None
    return int(cuenta.id)


async def test_numero_version_unicidad(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    db_session.add(_version(numero=1, codigo="A", inicio=date(2026, 1, 1), fin=date(2026, 12, 31)))
    await db_session.flush()
    db_session.add(_version(numero=1, codigo="B", inicio=date(2027, 1, 1), fin=date(2027, 12, 31)))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_proyeccion_unicidad(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    version = _version()
    db_session.add(version)
    await db_session.flush()
    account_id = await _plan_4300(db_session)
    db_session.add(
        CatalogoCuenta(
            empresa_id=10,
            version_id=version.id,
            account_id=account_id,
            codigo_version="4300",
            nombre_version="Clientes (euros)",
            estado=EstadoCuentaVersion.igual,
        )
    )
    await db_session.flush()
    db_session.add(
        CatalogoCuenta(
            empresa_id=10,
            version_id=version.id,
            account_id=account_id,
            codigo_version="4300",
            nombre_version="Duplicada",
            estado=EstadoCuentaVersion.igual,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_fk_compuesta_empresa(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    version = _version()
    db_session.add(version)
    await db_session.flush()
    account_id = await _plan_4300(db_session)
    db_session.add(
        CatalogoCuenta(
            empresa_id=20,
            version_id=version.id,
            account_id=account_id,
            codigo_version="4300",
            nombre_version="Cross",
            estado=EstadoCuentaVersion.igual,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_solape_vigencia_trigger(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    db_session.add(_version(numero=1, inicio=date(2026, 1, 1), fin=date(2026, 12, 31)))
    await db_session.flush()
    db_session.add(
        _version(
            numero=2,
            codigo="SOLAPADA",
            inicio=date(2026, 6, 1),
            fin=date(2027, 6, 30),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_rangos_contiguos_sin_solape(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    db_session.add(_version(numero=1, inicio=date(2026, 1, 1), fin=date(2026, 12, 31)))
    await db_session.flush()
    db_session.add(
        _version(
            numero=2,
            codigo="SIGUIENTE",
            inicio=date(2027, 1, 1),
            fin=date(2027, 12, 31),
        )
    )
    await db_session.flush()
    total = (
        await db_session.scalar(
            select(func.count()).select_from(CatalogoVersion).where(
                CatalogoVersion.empresa_id == 10
            )
        )
        or 0
    )
    assert int(total) == 2


async def test_reclasificacion_importe_negativo_rechazado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    version = _version()
    db_session.add(version)
    await db_session.flush()
    cuenta_destino_plan = await _plan_4300(db_session)
    cuenta_origen_plan = await db_session.scalar(
        select(AccountPlan.id).where(
            AccountPlan.tenant_id == 10, AccountPlan.code == "4000"
        )
    )
    assert cuenta_origen_plan is not None
    destino = CatalogoCuenta(
        empresa_id=10,
        version_id=version.id,
        account_id=cuenta_destino_plan,
        codigo_version="4300",
        nombre_version="Destino",
        estado=EstadoCuentaVersion.igual,
    )
    db_session.add(destino)
    await db_session.flush()
    origen = CatalogoCuenta(
        empresa_id=10,
        version_id=version.id,
        account_id=int(cuenta_origen_plan),
        codigo_version="4000",
        nombre_version="Origen",
        estado=EstadoCuentaVersion.suprimida,
    )
    db_session.add(origen)
    await db_session.flush()
    mapeo = MapeoCuenta(
        empresa_id=10,
        version_origen_id=version.id,
        version_destino_id=version.id,
        cuenta_origen_id=origen.id,
        cuenta_destino_id=destino.id,
        tipo_movimiento=TipoMovimiento.suprimida,
        requiere_reclasificacion=True,
    )
    db_session.add(mapeo)
    await db_session.flush()
    db_session.add(
        ReclasificacionSaldo(
            empresa_id=10,
            version_destino_id=version.id,
            mapeo_id=mapeo.id,
            cuenta_origen_id=int(cuenta_origen_plan),
            cuenta_destino_id=destino.id,
            importe=Decimal("-1.0000"),
            estado=EstadoReclasificacion.borrador,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


def test_reclasificacion_importe_numerico():
    tipo = ReclasificacionSaldo.__table__.c.importe.type
    assert str(tipo) == "NUMERIC(18, 4)"
