"""Apertura del ejercicio vía API (SPEC-009 T016, quickstart Scenarios 1-3)."""

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


def test_apertura_completa(ciclo_client):
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))

    r = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["ejercicio"] == 2027
    assert body["numero_asiento"] == 1
    assert body["importe_total_debe"] == "5000.0000"
    assert body["total_lineas"] == 2

    estado = client.get(
        "/api/v1/ciclo/apertura/estado",
        params={"ejercicio": 2027},
        headers=_hh(token, 10),
    ).json()
    assert estado["estado"] == "con_apertura"
    assert estado["asiento_apertura_id"] == body["asiento_id"]


def test_apertura_duplicada_rechazada(ciclo_client):
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))

    primero = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert primero.status_code == 201

    segundo = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert segundo.status_code == 409
    assert segundo.json()["detail"]["code"] == "ejercicio_ya_abierto"


def test_apertura_sin_cierre_previo_rechazada(ciclo_client):
    client, token, factory = ciclo_client
    from conftest import _correr

    async def _sin_cierre() -> None:
        async with factory() as session:
            session.add(
                FiscalYear(
                    empresa_id=10,
                    year=2026,
                    date_start=date(2026, 1, 1),
                    date_end=date(2026, 12, 31),
                    is_closed=False,
                    cierre_entry_id=None,
                )
            )
            session.add(
                EjercicioContable(
                    empresa_id=10,
                    ejercicio=2027,
                    fecha_inicio=date(2027, 1, 1),
                    fecha_fin=date(2027, 12, 31),
                    estado=EjercicioEstado.abierto,
                )
            )
            await session.commit()

    _correr(_sin_cierre())

    r = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_estado_reporta_abierto_y_no_definido(ciclo_client):
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))

    estado_prev = client.get(
        "/api/v1/ciclo/apertura/estado",
        params={"ejercicio": 2026},
        headers=_hh(token, 10),
    ).json()
    assert estado_prev["estado"] == "cerrado"

    estado_incierto = client.get(
        "/api/v1/ciclo/apertura/estado",
        params={"ejercicio": 2030},
        headers=_hh(token, 10),
    ).json()
    assert estado_incierto["estado"] == "no_definido"


def test_anulacion_y_regeneracion(ciclo_client):
    """quickstart Scenario 3: anular apertura errónea y regenerarla."""
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))

    apertura = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert apertura.status_code == 201

    anulacion = client.post(
        "/api/v1/ciclo/apertura/anular",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert anulacion.status_code == 200
    assert anulacion.json()["estado"] == "apertura_anulada"

    estado_anulada = client.get(
        "/api/v1/ciclo/apertura/estado",
        params={"ejercicio": 2027},
        headers=_hh(token, 10),
    ).json()
    assert estado_anulada["estado"] == "apertura_anulada"

    regenerada = client.post(
        "/api/v1/ciclo/apertura/regenerar",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert regenerada.status_code == 201
    assert regenerada.json()["regenerada"] is True
    assert regenerada.json()["numero_asiento"] == 3


def test_anular_sin_apertura_rechaza_404(ciclo_client):
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))

    r = client.post(
        "/api/v1/ciclo/apertura/anular",
        json={"ejercicio": 2027},
        headers=_hh(token, 10),
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "sin_apertura"


def test_apertura_destino_cerrado_rechazada(ciclo_client):
    """D8: no se permite abrir/reabrir un ejercicio ya cerrado distinto del previo."""
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))

    r = client.post(
        "/api/v1/ciclo/apertura",
        json={"ejercicio": 2026},
        headers=_hh(token, 10),
    )
    assert r.status_code in (409, 422)
    assert r.json()["detail"]["code"] in ("ejercicio_cerrado", "ejercicio_no_definido")


def test_apertura_tras_regenerar_sigue_bloqueada(ciclo_client):
    """FR-004: nunca hay dos aperturas vivas; tras regenerar, otro POST falla 409."""
    client, token, factory = ciclo_client
    from conftest import _correr

    _correr(_saldos_previo(factory, 10, 2026))

    client.post("/api/v1/ciclo/apertura", json={"ejercicio": 2027}, headers=_hh(token, 10))
    client.post("/api/v1/ciclo/apertura/anular", json={"ejercicio": 2027}, headers=_hh(token, 10))
    regenerar = client.post(
        "/api/v1/ciclo/apertura/regenerar", json={"ejercicio": 2027}, headers=_hh(token, 10)
    )
    assert regenerar.status_code == 201

    tercera = client.post(
        "/api/v1/ciclo/apertura", json={"ejercicio": 2027}, headers=_hh(token, 10)
    )
    assert tercera.status_code == 409
    assert tercera.json()["detail"]["code"] == "ejercicio_ya_abierto"