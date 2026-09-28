"""Cuentas suprimidas y seleccion parcial (SPEC-025 T034).

Una suprimida con saldo sin destino rechaza el preview con 422
``sin_destino``; la confirmacion admite seleccionar un subconjunto de los
items del preview y valida duplicados/ajenos (422 ``item_invalido``).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from models.catalog.reclasificacion_saldo import ReclasificacionSaldo
from services.catalog.errores import CatalogoError
from services.catalog.importacion_catalogo import importar_catalogo, parsear_csv
from services.catalog.reclasificacion_saldos import (
    confirmar_reclasificacion,
    preview_reclasificacion,
)
from tests.unit.catalogo_support import (
    objetivo_2026,
    plan_ids,
    postear,
    sembrar_base,
)

CSV_BAJA = (
    "operacion,codigo,nombre,padre_codigo,destino_codigo\n"
    "baja,4300,Clientes,,\n"
)


async def _objetivo_doble(db) -> str:
    objetivo = await objetivo_2026(
        db,
        operaciones=[
            {
                "operacion": "alta",
                "codigo": "4310",
                "nombre": "Clientes pagos",
                "padre_codigo": "431",
            },
            {
                "operacion": "renombrado",
                "codigo": "4300",
                "nombre": "Clientes euros",
                "destino_codigo": "4310",
            },
            {
                "operacion": "renombrado",
                "codigo": "4000",
                "nombre": "Proveedores euros",
                "destino_codigo": "4100",
            },
        ],
    )
    return str(objetivo.id)


async def test_suprimida_sin_destino_rechaza_preview(db_session):
    await sembrar_base(db_session)
    ids = await plan_ids(db_session)
    await postear(
        db_session,
        10,
        date(2025, 6, 30),
        [
            {"account_id": ids["4300"], "debit": "900.0000", "credit": "0"},
            {"account_id": ids["1110"], "debit": "0", "credit": "900.0000"},
        ],
    )
    importo = await importar_catalogo(
        db_session,
        empresa_id=10,
        codigo_version="NORMA-2026",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        operaciones=parsear_csv(CSV_BAJA),
        mapeo=[],
        actor="test",
    )

    with pytest.raises(CatalogoError) as exc:
        await preview_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=importo["version_id"],
            ejercicio=2025,
        )
    assert exc.value.code == "sin_destino"
    assert exc.value.status_code == 422


async def test_seleccion_parcial_y_duplicados(db_session):
    await sembrar_base(db_session)
    objetivo = await _objetivo_doble(db_session)
    ids = await plan_ids(db_session)
    await postear(
        db_session,
        10,
        date(2025, 6, 30),
        [
            {"account_id": ids["4300"], "debit": "500.0000", "credit": "0"},
            {"account_id": ids["1110"], "debit": "0", "credit": "500.0000"},
        ],
        concepto="Cobro",
    )
    await postear(
        db_session,
        10,
        date(2025, 7, 15),
        [
            {"account_id": ids["4000"], "debit": "300.0000", "credit": "0"},
            {"account_id": ids["1320"], "debit": "0", "credit": "300.0000"},
        ],
        concepto="Pago",
    )

    preview = await preview_reclasificacion(
        db_session, empresa_id=10, version_id=objetivo, ejercicio=2025
    )
    assert [i["codigo_origen"] for i in preview["items"]] == ["4000", "4300"]
    item_4300 = next(i for i in preview["items"] if i["codigo_origen"] == "4300")

    with pytest.raises(CatalogoError) as exc:
        await confirmar_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=objetivo,
            ejercicio=2025,
            items=[item_4300, item_4300],
            actor="test",
        )
    assert exc.value.code == "item_invalido"

    with pytest.raises(CatalogoError) as exc:
        await confirmar_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=objetivo,
            ejercicio=2025,
            items=[{"cuenta_origen_id": 999999999}],
            actor="test",
        )
    assert exc.value.code == "item_invalido"

    resultado = await confirmar_reclasificacion(
        db_session,
        empresa_id=10,
        version_id=objetivo,
        ejercicio=2025,
        items=[item_4300],
        actor="test",
    )
    assert resultado["reclasificaciones"] == 1
    assert resultado["total_importe"] == "500.0000"

    entry_id = uuid.UUID(resultado["asientos"][0]["asiento_id"])
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == entry_id
            )
        )
    ).all()
    assert {l.cuenta for l in lineas} == {"4300", "4310"}
    assert sum((l.debe for l in lineas), Decimal(0)) == Decimal("500.0000")

    filas = (
        await db_session.scalars(
            select(ReclasificacionSaldo).where(
                ReclasificacionSaldo.empresa_id == 10,
                ReclasificacionSaldo.version_destino_id == uuid.UUID(objetivo),
            )
        )
    ).all()
    assert len(filas) == 1
    assert filas[0].cuenta_origen_id == ids["4300"]
