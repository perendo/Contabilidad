"""Integración US2 completa (SPEC-016 T031).

Con saldos vivos en USD y tipo de cierre, la valoración genera un asiento
balanceado 6680/7690, persiste DiferenciaCambio y la segunda llamada -> 409.
"""

from __future__ import annotations

import uuid as _uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.monedas.diferencia_cambio import DiferenciaCambio


def test_valoracion_completa_asiento_balanceado_y_persistido(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")

    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["n"] == 2
    asiento_val = _uuid.UUID(cuerpo["asiento_id"])

    # El asiento es POSTED y balanceado (constitución I)
    async def _consulta(session):
        entrada = await session.get(JournalEntry, asiento_val)
        lineas = (
            await session.execute(
                select(JournalEntryLine.debe, JournalEntryLine.haber)
                .where(JournalEntryLine.journal_entry_id == asiento_val)
            )
        ).all()
        diferencias = (
            await session.execute(
                select(DiferenciaCambio).where(DiferenciaCambio.empresa_id == 10)
            )
        ).scalars().all()
        return entrada, lineas, diferencias

    entrada, lineas, diferencias = fx.run(fx.consultar(_consulta))
    assert entrada is not None
    assert entrada.estado == JournalEntryEstado.POSTED
    debe = sum(Decimal(l.debe) for l in lineas)
    haber = sum(Decimal(l.haber) for l in lineas)
    assert debe == haber == Decimal("30.0000")
    assert len(diferencias) == 2
    assert all(d.asiento_id == asiento_val for d in diferencias)


def test_segunda_valoracion_409(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    primera = fx.post("/api/v1/valoraciones", empresa_id=10,
                      json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert primera.status_code == 200
    segunda = fx.post("/api/v1/valoraciones", empresa_id=10,
                      json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert segunda.status_code == 409


def test_listado_diferencias_con_filtros(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    fx.post("/api/v1/valoraciones", empresa_id=10,
            json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})

    todos = fx.get(10, "/api/v1/diferencias-cambio", ejercicio=2026)
    assert todos.json()["total"] == 2
    por_cuenta = fx.get(10, "/api/v1/diferencias-cambio", ejercicio=2026, cuenta_id=fx.cuentas(10)["4300"])
    assert por_cuenta.json()["total"] == 1
    assert por_cuenta.json()["items"][0]["cuenta"] == "4300"
    assert por_cuenta.json()["items"][0]["diferencia"] == "15.0000"
    assert por_cuenta.json()["items"][0]["tipo"] == "ganancia"