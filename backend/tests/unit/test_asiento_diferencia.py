"""Asiento de diferencia de cambio balanceado (SPEC-016 T025).

El asiento de valoración cuadra exacto (Debe == Haber) y los saldos previos
del asiento original no se modifican (constitución II).
"""

from __future__ import annotations

import uuid as _uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.monedas.diferencia_cambio import DiferenciaCambio


def _preparar_valoracion(fx) -> dict:
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp_i = fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    assert resp_i.status_code == 201
    asiento_original = resp_i.json()["asiento_id"]
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp.status_code == 200
    return {"valoracion": resp.json(), "asiento_original": asiento_original}


def test_asiento_valoracion_balanceado(forex_client):
    fx = forex_client
    datos = _preparar_valoracion(fx)
    asiento_val = _uuid.UUID(datos["valoracion"]["asiento_id"])

    async def _consulta(session):
        entrada = await session.get(JournalEntry, asiento_val)
        filas = (
            await session.execute(
                select(JournalEntryLine.debe, JournalEntryLine.haber)
                .where(JournalEntryLine.journal_entry_id == asiento_val)
            )
        ).all()
        return entrada, filas

    entrada, filas = fx.run(fx.consultar(_consulta))
    assert entrada is not None
    assert entrada.estado == JournalEntryEstado.POSTED
    assert entrada.tipo == JournalEntryTipo.ADJUSTMENT
    debe = sum(Decimal(f.debe) for f in filas)
    haber = sum(Decimal(f.haber) for f in filas)
    assert debe == haber == Decimal("30.0000")  # 2 diferencias de 15


def test_saldos_original_no_modificados(forex_client):
    fx = forex_client
    datos = _preparar_valoracion(fx)
    asiento_original = _uuid.UUID(datos["asiento_original"])

    async def _consulta(session):
        filas = (
            await session.execute(
                select(JournalEntryLine.debe, JournalEntryLine.haber)
                .where(JournalEntryLine.journal_entry_id == asiento_original)
            )
        ).all()
        return [Decimal(f.debe) - Decimal(f.haber) for f in filas]

    saldos = fx.run(fx.consultar(_consulta))
    # Dos líneas: 4300 debe 1085 / 5720 haber 1085; los importes no se tocaron
    assert sum(saldos) == 0
    assert saldos == [Decimal("1085.0000"), Decimal("-1085.0000")]


def test_diferencia_persistida_con_asiento_enlazado(forex_client):
    fx = forex_client
    datos = _preparar_valoracion(fx)
    asiento_val = _uuid.UUID(datos["valoracion"]["asiento_id"])

    async def _consulta(session):
        filas = (
            await session.execute(
                select(DiferenciaCambio.asiento_id).where(
                    DiferenciaCambio.empresa_id == 10
                )
            )
        ).all()
        return [f[0] if f[0] is not None else None for f in filas]

    enlazados = fx.run(fx.consultar(_consulta))
    assert all(x == asiento_val for x in enlazados)
    assert len(enlazados) == 2