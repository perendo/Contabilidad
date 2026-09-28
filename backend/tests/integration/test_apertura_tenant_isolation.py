"""Aislamiento multi-tenant de la apertura (SPEC-009 T017, FR-001/D9)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado


def _hh(token, empresa_id):
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa_id)}


async def _saldos_previo(factory, empresa_id: int, year: int) -> None:
    async with factory() as session:
        ids = {
            code: ident
            for code, ident in (
                await session.execute(
                    select(AccountPlan.code, AccountPlan.id).where(
                        AccountPlan.tenant_id == empresa_id,
                        AccountPlan.is_active.is_(True),
                    )
                )
            ).all()
        }
        entry = JournalEntry(
            empresa_id=empresa_id,
            ejercicio=year,
            fecha=datetime(year, 6, 30, tzinfo=timezone.utc).date(),
            tipo=JournalEntryTipo.GENERAL,
            concepto=f"Saldos {year}",
            estado=JournalEntryEstado.POSTED,
            numero_asiento=1,
        )
        session.add(entry)
        await session.flush()
        session.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=entry.id,
                account_id=ids["1110"],
                line_no=1,
                cuenta="1110",
                debe=Decimal("0.0000"),
                haber=Decimal("5000.0000"),
            )
        )
        session.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=entry.id,
                account_id=ids["2100"],
                line_no=2,
                cuenta="2100",
                debe=Decimal("5000.0000"),
                haber=Decimal("0.0000"),
            )
        )
        session.add(
            FiscalYear(
                empresa_id=empresa_id,
                year=year,
                date_start=date(year, 1, 1),
                date_end=date(year, 12, 31),
                is_closed=True,
                cierre_entry_id=None,
            )
        )
        session.add(
            EjercicioContable(
                empresa_id=empresa_id,
                ejercicio=year + 1,
                fecha_inicio=date(year + 1, 1, 1),
                fecha_fin=date(year + 1, 12, 31),
                estado=EjercicioEstado.abierto,
            )
        )
        await session.commit()


def test_empresa_a_abre_y_b_no_la_ve(ciclo_client):
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))
    _correr(_saldos_previo(factory, 20, 2026))

    a = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert a.status_code == 201

    estado_b = client.get(
        "/api/v1/ciclo/apertura/estado",
        params={"ejercicio": 2027},
        headers=_hh(token, 20),
    ).json()
    assert estado_b["estado"] == "abierto"
    assert estado_b["asiento_apertura_id"] is None

    anular_b = client.post(
        "/api/v1/ciclo/apertura/anular",
        json={"ejercicio": 2027},
        headers=_hh(token, 20),
    )
    assert anular_b.status_code == 404
    assert anular_b.json()["detail"]["code"] == "sin_apertura"

    estado_a = client.get(
        "/api/v1/ciclo/apertura/estado",
        params={"ejercicio": 2027},
        headers=_hh(token, 10),
    ).json()
    assert estado_a["estado"] == "con_apertura"


def test_cada_empresa_abre_su_propio_ejercicio(ciclo_client):
    """FR-001: la apertura de A no bloquea la suya propia de B."""
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))
    _correr(_saldos_previo(factory, 20, 2026))

    a = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert a.status_code == 201

    b = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 20),
    )
    assert b.status_code == 201
    assert b.json()["numero_asiento"] == 1

    estado_b = client.get(
        "/api/v1/ciclo/apertura/estado",
        params={"ejercicio": 2027},
        headers=_hh(token, 20),
    ).json()
    assert estado_b["estado"] == "con_apertura"