"""T043: Constitución I, II y III aplicadas a los centros de coste.

Partida doble: todo asiento POSTED con imputaciones permanece balanceado.
Inmutabilidad: la traza de un asiento posteado es append-only (triggers de
nivel DB rechazan UPDATE/DELETE). Multi-tenancy: la traza y los centros filtran
por empresa_id, y la clave (empresa_id, asiento_id, linea_id) impide duplicar
la imputación de una misma línea.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryLine
from models.costcenters.imputacion import ImputacionCentro
from models.costcenters.jerarquia import JerarquiaCentro
from services.costcenters.centros import crear_centro
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


async def _asiento_con_imputacion(db_session, empresa_id, importe: str, centro_id):
    c430 = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "4300"
        )
    )
    c570 = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "5720"
        )
    )
    assert c430 is not None and c570 is not None
    return await crear_asiento_multilinea(
        db_session,
        empresa_id=empresa_id,
        fecha=date(2026, 5, 14),
        concepto="Constitución",
        lineas=[
            {"cuenta": c430.code, "debe": importe, "haber": "0", "centro_coste_id": str(centro_id)},
            {"cuenta": c570.code, "debe": "0", "haber": importe},
        ],
    )


async def test_partida_doble_en_asientos_con_imputaciones(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    c10 = await crear_centro(db_session, empresa_id=10, codigo="C10", nombre="C10", tipo="proyecto")
    c20 = await crear_centro(db_session, empresa_id=20, codigo="C20", nombre="C20", tipo="proyecto")
    await _asiento_con_imputacion(db_session, 10, "333.4400", c10["id"])
    await _asiento_con_imputacion(db_session, 20, "111.2200", c20["id"])

    ids = set(
        (await db_session.scalars(
            select(ImputacionCentro.asiento_id).where(ImputacionCentro.empresa_id.in_([10, 20]))
        )).all()
    )
    for asiento_id in ids:
        debe = await db_session.scalar(
            select(func.sum(JournalEntryLine.debe)).where(JournalEntryLine.journal_entry_id == asiento_id)
        )
        haber = await db_session.scalar(
            select(func.sum(JournalEntryLine.haber)).where(JournalEntryLine.journal_entry_id == asiento_id)
        )
        assert debe is not None and haber is not None
        assert debe == haber


async def test_update_traza_posteada_rechazado_a_nivel_db(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="IMU", nombre="Inmutable", tipo="proyecto")
    entrada = await _asiento_con_imputacion(db_session, 10, "40.0000", centro["id"])
    assert entrada.estado == "POSTED"

    traza = await db_session.scalar(
        select(ImputacionCentro).where(ImputacionCentro.asiento_id == entrada.id)
    )
    assert traza is not None

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("UPDATE imputacion_centro SET periodo = 9 WHERE id = :i"),
            {"i": traza.id.hex},
        )
        await db_session.flush()


async def test_delete_traza_posteada_rechazado_a_nivel_db(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="IMD", nombre="Inmutable", tipo="proyecto")
    entrada = await _asiento_con_imputacion(db_session, 10, "40.0000", centro["id"])
    assert entrada.estado == "POSTED"

    traza = await db_session.scalar(
        select(ImputacionCentro).where(ImputacionCentro.asiento_id == entrada.id)
    )
    assert traza is not None

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM imputacion_centro WHERE id = :i"),
            {"i": traza.id.hex},
        )
        await db_session.flush()


async def test_centro_con_imputaciones_no_se_borra_a_nivel_db(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="NOD", nombre="Nod", tipo="proyecto")
    await _asiento_con_imputacion(db_session, 10, "1.0000", centro["id"])

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM centro_coste WHERE id = :i"),
            {"i": centro["id"].replace("-", "")},
        )
        await db_session.flush()


async def test_traza_y_centros_filtran_por_empresa(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    c10 = await crear_centro(db_session, empresa_id=10, codigo="F10", nombre="F10", tipo="proyecto")
    await _asiento_con_imputacion(db_session, 10, "50.0000", c10["id"])

    total_20 = await db_session.scalar(
        select(func.count()).select_from(
            select(ImputacionCentro).where(ImputacionCentro.empresa_id == 20).subquery()
        )
    )
    assert int(total_20 or 0) == 0

    pares_20 = await db_session.scalar(
        select(func.count()).select_from(
            select(JerarquiaCentro).where(JerarquiaCentro.empresa_id == 20).subquery()
        )
    )
    assert int(pares_20 or 0) == 0

    # La clave (empresa_id, asiento_id, linea_id) impide una segunda imputación
    # de la misma línea del mismo asiento.
    linea = await db_session.scalar(
        select(JournalEntryLine).where(
            JournalEntryLine.empresa_id == 10,
            JournalEntryLine.journal_entry_id.in_(
                select(JournalEntry.id).where(JournalEntry.empresa_id == 10)
            ),
        )
    )
    assert linea is not None
    db_session.add(
        ImputacionCentro(
            empresa_id=10,
            asiento_id=linea.journal_entry_id,
            linea_id=linea.id,
            centro_coste_id=uuid.UUID(c10["id"]),
            periodo=5,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()