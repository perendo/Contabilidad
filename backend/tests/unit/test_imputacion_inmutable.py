"""T025: Inmutabilidad de las imputaciones (SPEC-017 US2, constitución II).

Líneas POSTED/CANCELLED: imputar/quitar responde 409 `linea_posteada`; la
reimputación se hace creando un asiento ADJUSTMENT (motor). Líneas de borrador:
se puede imputar, reimputar y quitar libremente.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntryLine
from services.costcenters.centros import crear_centro
from services.costcenters.errores import CostcenterError
from services.costcenters.imputacion import (
    imputar_linea,
    listar_imputaciones,
    quitar_imputacion,
    rectificar_imputacion,
)
from services.journal.entry_service import crear_borrador
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


async def _cuenta(db_session, empresa_id, code: str) -> AccountPlan:
    cuenta = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
        )
    )
    assert cuenta is not None
    return cuenta


def _uid(s: str) -> uuid.UUID:
    return uuid.UUID(s)


async def _puesto(db_session, empresa_id):
    """Asiento POSTED con la línea 4300 imputada a `centro`."""
    await sembrar_empresa_pgc(db_session, empresa_id)
    centro = await crear_centro(db_session, empresa_id=empresa_id, codigo="P1", nombre="Posteado", tipo="proyecto")
    c430, c572 = await _cuenta(db_session, empresa_id, "4300"), await _cuenta(db_session, empresa_id, "5720")
    entrada = await crear_asiento_multilinea(
        db_session,
        empresa_id=empresa_id,
        fecha=date(2026, 5, 14),
        concepto="Gasto",
        lineas=[
            {"cuenta": c430.code, "debe": "60.0000", "haber": "0", "centro_coste_id": str(centro["id"])},
            {"cuenta": c572.code, "debe": "0", "haber": "60.0000"},
        ],
    )
    linea = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entrada.id)
        )
    ).all()
    linea_debe = next(l for l in linea if l.debe > 0)
    return centro, entrada, linea_debe


async def test_linea_posteada_rechaza_imputar(db_session):
    _, entrada, linea = await _puesto(db_session, 10)
    otro = await crear_centro(db_session, empresa_id=10, codigo="P2", nombre="Otro", tipo="proyecto")
    with pytest.raises(CostcenterError) as exc:
        await imputar_linea(
            db_session, empresa_id=10, asiento_id=entrada.id,
            linea_id=linea.id, centro_coste_id=_uid(otro["id"]),
        )
    assert exc.value.code == "linea_posteada"


async def test_linea_posteada_rechaza_quitar(db_session):
    _, entrada, linea = await _puesto(db_session, 10)
    with pytest.raises(CostcenterError) as exc:
        await quitar_imputacion(
            db_session, empresa_id=10, asiento_id=entrada.id, linea_id=linea.id
        )
    assert exc.value.code == "linea_posteada"


async def test_rectificar_posteada_crea_adjustment(db_session):
    centro, entrada, linea = await _puesto(db_session, 10)
    destino = await crear_centro(db_session, empresa_id=10, codigo="P3", nombre="Destino", tipo="proyecto")

    resultado = await rectificar_imputacion(
        db_session, empresa_id=10, asiento_id=entrada.id,
        linea_id=linea.id, centro_coste_id=_uid(destino["id"]),
    )
    assert resultado["asiento_original_id"] == str(entrada.id)
    assert resultado["asiento_rectificativo_id"]
    assert resultado["numero_asiento"] is not None

    # El original queda intacto (sigue imputado a `centro`)
    linea_tras = await db_session.get(JournalEntryLine, linea.id)
    assert str(linea_tras.centro_coste_id) == str(centro["id"])


async def test_borrador_admite_imputar_reimputar_y_quitar(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    c430, c572 = await _cuenta(db_session, 10, "4300"), await _cuenta(db_session, 10, "5720")
    centro_a = await crear_centro(db_session, empresa_id=10, codigo="B1", nombre="A", tipo="proyecto")
    centro_b = await crear_centro(db_session, empresa_id=10, codigo="B2", nombre="B", tipo="proyecto")

    borrador = await crear_borrador(
        db_session,
        empresa_id=10,
        fecha=date(2026, 5, 14),
        concepto="Borrador",
        lineas=[
            {"account_id": c430.id, "debit": Decimal("50.0000"), "credit": Decimal(0)},
            {"account_id": c572.id, "debit": Decimal(0), "credit": Decimal("50.0000")},
        ],
    )
    linea = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == borrador.id)
        )
    ).all()
    linea_debe = next(l for l in linea if l.debe > 0)

    await imputar_linea(db_session, empresa_id=10, asiento_id=borrador.id, linea_id=linea_debe.id, centro_coste_id=_uid(centro_a["id"]))
    assert (await db_session.scalars(select(JournalEntryLine).where(JournalEntryLine.id == linea_debe.id))).one().centro_coste_id == _uid(centro_a["id"])

    # Reimputar (upsert de la traza)
    await imputar_linea(db_session, empresa_id=10, asiento_id=borrador.id, linea_id=linea_debe.id, centro_coste_id=_uid(centro_b["id"]))
    traza = await listar_imputaciones(db_session, empresa_id=10, asiento_id=borrador.id)
    assert traza["total"] == 1
    assert traza["items"][0]["centro_coste_id"] == str(centro_b["id"])

    # Quitar
    await quitar_imputacion(db_session, empresa_id=10, asiento_id=borrador.id, linea_id=linea_debe.id)
    assert (await db_session.scalars(select(JournalEntryLine).where(JournalEntryLine.id == linea_debe.id))).one().centro_coste_id is None


async def test_quitar_sin_imputacion_409(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    c430, c572 = await _cuenta(db_session, 10, "4300"), await _cuenta(db_session, 10, "5720")
    borrador = await crear_borrador(
        db_session,
        empresa_id=10,
        fecha=date(2026, 5, 14),
        concepto="Sin imputar",
        lineas=[
            {"account_id": c430.id, "debit": Decimal("10.0000"), "credit": Decimal(0)},
            {"account_id": c572.id, "debit": Decimal(0), "credit": Decimal("10.0000")},
        ],
    )
    linea = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == borrador.id)
        )
    ).all()[0]
    with pytest.raises(CostcenterError) as exc:
        await quitar_imputacion(db_session, empresa_id=10, asiento_id=borrador.id, linea_id=linea.id)
    assert exc.value.code == "imputacion_no_existente"
