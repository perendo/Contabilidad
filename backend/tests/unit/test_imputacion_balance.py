"""T023: Balance estricto al imputar (SPEC-017 US2, constitución I).

Imputar un centro a una línea nunca altera Debe/Haber: la suma del asiento
permanece invariante (partida doble) y la traza `imputacion_centro` refleja
la dimensión por línea sin tocar importes.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntryLine
from models.costcenters.imputacion import ImputacionCentro
from services.costcenters.centros import crear_centro
from services.journal.entry_service import crear_borrador
from tests.conftest import sembrar_empresa_pgc


async def _cuenta(db_session, empresa_id, code: str) -> AccountPlan:
    cuenta = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
        )
    )
    assert cuenta is not None
    return cuenta


async def _lineas_pgt(db_session, empresa_id):
    c430 = await _cuenta(db_session, empresa_id, "4300")
    c572 = await _cuenta(db_session, empresa_id, "5720")
    return c430, c572


async def _borrador_imputable(db_session, empresa_id, importe: Decimal, centro_id=None):
    c430, c572 = await _lineas_pgt(db_session, empresa_id)
    return await crear_borrador(
        db_session,
        empresa_id=empresa_id,
        fecha=date(2026, 5, 14),
        concepto="Gasto imputado",
        lineas=[
            {
                "account_id": c430.id,
                "debit": importe,
                "credit": Decimal(0),
                "detail": "Línea imputada",
                "centro_coste_id": centro_id,
            },
            {
                "account_id": c572.id,
                "debit": Decimal(0),
                "credit": importe,
                "detail": "Contrapartida",
            },
        ],
    )


async def test_imputar_no_cambia_debe_ni_haber(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="N1", nombre="Nuevo", tipo="departamento")
    borrador = await _borrador_imputable(db_session, 10, Decimal("100.0000"))

    lineas_antes = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == borrador.id
            )
        )
    ).all()
    suma_antes = sum((l.debe + l.haber for l in lineas_antes), Decimal(0))

    linea_debe = next(l for l in lineas_antes if l.debe > 0)
    from services.costcenters.imputacion import imputar_linea

    await imputar_linea(
        db_session,
        empresa_id=10,
        asiento_id=borrador.id,
        linea_id=linea_debe.id,
        centro_coste_id=uuid.UUID(centro["id"]),
    )

    lineas_despues = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == borrador.id
            )
        )
    ).all()
    assert not [l for l in lineas_despues
                if l.id == linea_debe.id and l.debe != linea_debe.debe]
    assert sum((l.debe + l.haber for l in lineas_despues), Decimal(0)) == suma_antes

    traza = await db_session.scalar(
        select(ImputacionCentro).where(
            ImputacionCentro.empresa_id == 10,
            ImputacionCentro.linea_id == linea_debe.id,
        )
    )
    assert traza is not None
    assert str(traza.centro_coste_id) == str(centro["id"])
    assert traza.periodo == 5


async def test_motor_persiste_traza_y_balance(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="BV", nombre="Balance", tipo="proyecto")
    c430, c572 = await _lineas_pgt(db_session, 10)

    from services.journal.motor import crear_asiento_multilinea

    entrada = await crear_asiento_multilinea(
        db_session,
        empresa_id=10,
        fecha=date(2026, 5, 14),
        concepto="Gasto",
        lineas=[
            {"cuenta": c430.code, "debe": "125.5000", "haber": "0", "centro_coste_id": str(centro["id"])},
            {"cuenta": c572.code, "debe": "0", "haber": "125.5000"},
        ],
    )
    assert entrada.estado == "POSTED"

    total_debe = await db_session.scalar(
        select(func.sum(JournalEntryLine.debe)).where(
            JournalEntryLine.journal_entry_id == entrada.id
        )
    )
    total_haber = await db_session.scalar(
        select(func.sum(JournalEntryLine.haber)).where(
            JournalEntryLine.journal_entry_id == entrada.id
        )
    )
    assert Decimal(str(total_debe)) == Decimal("125.5000")
    assert Decimal(str(total_haber)) == Decimal("125.5000")

    trazas = (
        await db_session.scalars(
            select(ImputacionCentro).where(
                ImputacionCentro.empresa_id == 10,
                ImputacionCentro.asiento_id == entrada.id,
            )
        )
    ).all()
    assert len(trazas) == 1
    assert str(trazas[0].centro_coste_id) == str(centro["id"])


async def test_traza_ligada_a_linea_del_motor(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="TZ", nombre="Traza", tipo="proyecto")
    c430, c572 = await _lineas_pgt(db_session, 10)

    from services.journal.motor import crear_asiento_multilinea

    entrada = await crear_asiento_multilinea(
        db_session,
        empresa_id=10,
        fecha=date(2026, 5, 14),
        concepto="Gasto",
        lineas=[
            {"cuenta": c430.code, "debe": "80.0000", "haber": "0", "centro_coste_id": str(centro["id"])},
            {"cuenta": c572.code, "debe": "0", "haber": "80.0000"},
        ],
    )
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entrada.id)
        )
    ).all()
    linea_debe = next(l for l in lineas if l.debe > 0)
    assert str(linea_debe.centro_coste_id) == str(centro["id"])

    traza = await db_session.scalar(
        select(ImputacionCentro).where(
            ImputacionCentro.empresa_id == 10,
            ImputacionCentro.linea_id == linea_debe.id,
        )
    )
    assert traza is not None
    assert str(traza.centro_coste_id) == str(centro["id"])
    assert traza.periodo == 5
    assert traza.id is not None and isinstance(traza.id, uuid.UUID)