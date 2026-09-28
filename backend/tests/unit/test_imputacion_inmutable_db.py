"""T047: Inmutabilidad de la imputación a nivel DB (SPEC-017, constitución II).

Aunque el servicio bloquee la reasignación de líneas posteadas, la defensa en
profundidad son los triggers SQLite (y su equivalente `009_costcenters.sql` en
PostgreSQL): AFTER the fact, un UPDATE/DELETE directo sobre la traza de un
asiento POSTED es rechazado por la base de datos.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, text

from models.acct.account_plan import AccountPlan
from models.costcenters.imputacion import ImputacionCentro
from services.costcenters.centros import crear_centro
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


async def _posteado_imputado(db_session, empresa_id):
    await sembrar_empresa_pgc(db_session, empresa_id)
    centro = await crear_centro(db_session, empresa_id=empresa_id, codigo="DBN", nombre="DB", tipo="proyecto")
    c430 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == "4300")
    )
    c572 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == "5720")
    )
    entrada = await crear_asiento_multilinea(
        db_session,
        empresa_id=empresa_id,
        fecha=date(2026, 6, 1),
        concepto="DB inmutable",
        lineas=[
            {"cuenta": c430.code, "debe": "25.0000", "haber": "0", "centro_coste_id": str(centro["id"])},
            {"cuenta": c572.code, "debe": "0", "haber": "25.0000"},
        ],
    )
    traza = await db_session.scalar(
        select(ImputacionCentro).where(ImputacionCentro.asiento_id == entrada.id)
    )
    return entrada, traza, centro


async def test_update_imputacion_posteada_rechazado(db_session):
    _, traza, _ = await _posteado_imputado(db_session, 10)
    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text("UPDATE imputacion_centro SET periodo = 12 WHERE id = :i"),
            {"i": traza.id.hex},
        )
        await db_session.flush()
    assert "inmutable" in str(exc.value)


async def test_delete_imputacion_posteada_rechazado(db_session):
    _, traza, _ = await _posteado_imputado(db_session, 10)
    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text("DELETE FROM imputacion_centro WHERE id = :i"),
            {"i": traza.id.hex},
        )
        await db_session.flush()
    assert "inmutable" in str(exc.value)


async def test_delete_centro_con_imputacion_rechazado(db_session):
    _, _, centro = await _posteado_imputado(db_session, 10)
    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text("DELETE FROM centro_coste WHERE id = :i"),
            {"i": centro["id"].replace("-", "")},
        )
        await db_session.flush()
    assert "no se puede eliminar" in str(exc.value)


async def test_borrador_si_permite_delete_de_traza(db_session):
    """En borrador la traza no está congelada: el DELETE a nivel DB pasa."""
    import uuid
    from datetime import date as _d
    from decimal import Decimal

    from sqlalchemy import func

    from models.acct.journal import JournalEntryLine
    from services.costcenters.imputacion import imputar_linea
    from services.journal.entry_service import crear_borrador

    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="BRR", nombre="Draft", tipo="proyecto")
    c430 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 10, AccountPlan.code == "4300")
    )
    c572 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 10, AccountPlan.code == "5720")
    )
    borrador = await crear_borrador(
        db_session,
        empresa_id=10,
        fecha=_d(2026, 6, 1),
        concepto="Draft",
        lineas=[
            {"account_id": c430.id, "debit": Decimal("5.0000"), "credit": Decimal(0)},
            {"account_id": c572.id, "debit": Decimal(0), "credit": Decimal("5.0000")},
        ],
    )
    assert borrador.estado == "DRAFT"

    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == borrador.id)
        )
    ).all()
    linea = next(l for l in lineas if l.debe > 0)
    await imputar_linea(
        db_session, empresa_id=10, asiento_id=borrador.id,
        linea_id=linea.id, centro_coste_id=uuid.UUID(centro["id"]),
    )
    traza = await db_session.scalar(
        select(ImputacionCentro).where(ImputacionCentro.asiento_id == borrador.id)
    )
    assert traza is not None

    await db_session.execute(
        text("DELETE FROM imputacion_centro WHERE id = :i"),
        {"i": traza.id.hex},
    )
    await db_session.flush()

    quedan = await db_session.scalar(
        select(func.count()).select_from(
            select(ImputacionCentro).where(ImputacionCentro.empresa_id == 10).subquery()
        )
    )
    assert int(quedan or 0) == 0
