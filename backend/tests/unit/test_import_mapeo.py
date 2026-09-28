"""Importacion de la normativa y generacion de mapeos (SPEC-025 T024).

``importar_catalogo`` crea la version ``borrador`` con ``es_migracion=true``,
cuenta nuevas/renombradas/suprimidas/manifiestos (escenario esc3) y reporta
``pendientes_mapeo`` cuando una baja se queda sin destino.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from models.catalog.catalogo_cuenta import CatalogoCuenta, EstadoCuentaVersion
from models.catalog.catalogo_version import EstadoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta, OrigenMapeo, TipoMovimiento
from services.catalog.importacion_catalogo import importar_catalogo, parsear_csv
from tests.unit.catalogo_support import plan_ids, postear, sembrar_base

CSV_ES3 = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "renombrado,4300,Clientes euros,430,4310\n"
    "alta,4310,Clientes pagos,431,\n"
)


async def _importar(db, operaciones, fecha_inicio=date(2026, 1, 1), mapeo=None):
    return await importar_catalogo(
        db,
        empresa_id=10,
        codigo_version="NORMA-2026",
        fecha_inicio=fecha_inicio,
        fecha_fin=date(2026, 12, 31),
        operaciones=operaciones,
        mapeo=mapeo or [],
        actor="test",
    )


async def test_import_esc3_conteos(db_session):
    await sembrar_base(db_session)
    operaciones = parsear_csv(CSV_ES3)
    resultado = await _importar(db_session, operaciones)

    assert resultado["nuevas"] == 1
    assert resultado["renombradas"] == 1
    assert resultado["suprimidas"] == 0
    assert resultado["mapeos"] == 1
    assert resultado["pendientes_mapeo"] == []
    assert resultado["version_id"]

    filas = (
        await db_session.scalars(
            select(CatalogoCuenta).where(
                CatalogoCuenta.empresa_id == 10,
                CatalogoCuenta.version_id == uuid.UUID(resultado["version_id"]),
            )
        )
    ).all()
    por_codigo = {f.codigo_version: f for f in filas}
    assert por_codigo["4310"].estado == EstadoCuentaVersion.nueva
    assert por_codigo["4300"].estado == EstadoCuentaVersion.renombrada

    mapeo_ren = (
        await db_session.scalar(
            select(MapeoCuenta).where(
                MapeoCuenta.empresa_id == 10,
                MapeoCuenta.version_destino_id == por_codigo["4310"].version_id,
                MapeoCuenta.tipo_movimiento == TipoMovimiento.renombrada,
            )
        )
    )
    assert mapeo_ren is not None
    assert mapeo_ren.cuenta_destino_id == por_codigo["4310"].id
    assert mapeo_ren.requiere_reclasificacion is True


async def test_import_es_migracion_y_estado(db_session):
    await sembrar_base(db_session)
    resultado = await _importar(db_session, parsear_csv(CSV_ES3))
    from services.catalog._comun import obtener_version

    version = await obtener_version(db_session, 10, resultado["version_id"])
    assert version is not None
    assert version.estado == EstadoVersion.borrador
    assert version.es_migracion is True


async def test_import_baja_sin_destino_pendiente(db_session):
    await sembrar_base(db_session)
    csv = (
        "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
        "baja,4300,Clientes,,\n"
    )
    resultado = await _importar(db_session, parsear_csv(csv))
    assert resultado["suprimidas"] == 1
    assert resultado["pendientes_mapeo"] == [
        {"codigo": "4300", "motivo": "sin_destino"}
    ]


async def test_import_baja_con_saldo_es_bloqueante(db_session):
    await sembrar_base(db_session)
    ids = await plan_ids(db_session)
    await postear(
        db_session,
        10,
        date(2025, 6, 30),
        [
            {"account_id": ids["4300"], "debit": "100.0000", "credit": "0"},
            {"account_id": ids["1110"], "debit": "0", "credit": "100.0000"},
        ],
        concepto="Cobro cliente",
    )
    csv = (
        "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
        "baja,4300,Clientes,,\n"
    )
    resultado = await _importar(db_session, parsear_csv(csv))
    assert resultado["pendientes_mapeo"] == [
        {"codigo": "4300", "motivo": "saldo_no_cero"}
    ]


async def test_import_mapeo_explicito(db_session):
    await sembrar_base(db_session)
    csv = (
        "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
        "baja,4000,Proveedores,,\n"
    )
    resultado = await _importar(
        db_session,
        parsear_csv(csv),
        mapeo=[{"origen_codigo": "4000", "destino_codigo": "4100"}],
    )
    assert resultado["suprimidas"] == 1
    assert resultado["pendientes_mapeo"] == []
    assert resultado["mapeos"] == 1

    version_id = uuid.UUID(resultado["version_id"])
    mapeo = (
        await db_session.scalars(
            select(MapeoCuenta).where(
                MapeoCuenta.empresa_id == 10,
                MapeoCuenta.version_destino_id == version_id,
                MapeoCuenta.origen == OrigenMapeo.manifiesto,
            )
        )
    ).first()
    assert mapeo is not None
    assert mapeo.cuenta_destino_id is not None
    assert mapeo.requiere_reclasificacion is True
    assert mapeo.tipo_movimiento == TipoMovimiento.renombrada
