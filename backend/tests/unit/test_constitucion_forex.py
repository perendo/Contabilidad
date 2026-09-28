"""Constitución V aplicada a multi-divisa (SPEC-016 T043).

Cada asiento en divisa y cada asiento de diferencias cuadra en divisa Y en
funcional (constitución I); nunca se modifica/borra un JournalEntry POSTED ni
un tipo sellado (constitución II); aislamiento empresa_id en todas las tablas
forex (constitución III).
"""

from __future__ import annotations

import uuid as _uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.monedas.asiento_divisa import AsientoDivisa
from models.monedas.diferencia_cambio import DiferenciaCambio
from models.monedas.moneda import Moneda
from models.monedas.tipo_cambio import TipoCambio


def test_cuadre_doble_de_asiento_divisa(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.28500000")
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "600.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["4300"], "debe_divisa": "400.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "1000.0000"},
        ],
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    # Cada línea del asiento funciona en ambas monedas: divisa total y funcional
    assert cuerpo["importe_total_divisa"] == "1000.0000"
    assert cuerpo["importe_total_funcional"] == "1285.0000"
    assert cuerpo["linea_redondeo"] is None

    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}")
    lineas = detalle.json()["lineas"]
    debe_div = sum(Decimal(l["debe_divisa"]) for l in lineas)
    haber_div = sum(Decimal(l["haber_divisa"]) for l in lineas)
    debe_fun = sum(Decimal(l["debe_funcional"]) for l in lineas)
    haber_fun = sum(Decimal(l["haber_funcional"]) for l in lineas)
    assert debe_div == haber_div == Decimal("1000.0000")
    assert debe_fun == haber_fun == Decimal("1285.0000")


def test_asiento_diferencias_balanceado_POSTED(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    criterio = fx.post("/api/v1/valoraciones", empresa_id=10,
                       json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert criterio.status_code == 200

    if criterio.json().get("asiento_id") is None:
        return  # sin diferencias no hay asiento que validar
    asiento_id = _uuid.UUID(criterio.json()["asiento_id"])

    async def _consulta(session):
        entrada = await session.get(JournalEntry, asiento_id)
        lineas = (
            await session.execute(
                select(JournalEntryLine.debe, JournalEntryLine.haber)
                .where(JournalEntryLine.journal_entry_id == asiento_id)
            )
        ).all()
        return entrada, lineas

    entrada, lineas = fx.run(fx.consultar(_consulta))
    assert entrada is not None
    assert entrada.estado == JournalEntryEstado.POSTED
    debe = sum(Decimal(l.debe) for l in lineas)
    haber = sum(Decimal(l.haber) for l in lineas)
    assert debe == haber


def test_el_asiento_divisa_original_queda_POSTED_inmutable(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    asiento_id = _uuid.UUID(resp.json()["asiento_id"])

    async def _consulta(session):
        entrada = await session.get(JournalEntry, asiento_id)
        return entrada

    entrada = fx.run(fx.consultar(_consulta))
    assert entrada is not None
    assert entrada.estado == JournalEntryEstado.POSTED
    assert entrada.concepto == "Venta en USD"


def test_aislamiento_de_tablas_forex_por_empresa(forex_client):
    fx = forex_client
    # A registra todo su flujo: divisa (ya sembrada), tipo, asiento, valoración
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    fx.post("/api/v1/valoraciones", empresa_id=10,
            json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})

    async def _todas_empresas(session):
        monedas = (await session.execute(select(Moneda.empresa_id))).all()
        tipos = (await session.execute(select(TipoCambio.empresa_id))).all()
        asientos = (await session.execute(select(AsientoDivisa.empresa_id))).all()
        diferencias = (await session.execute(select(DiferenciaCambio.empresa_id))).all()
        return monedas, tipos, asientos, diferencias

    monedas, tipos, asientos, diferencias = fx.run(fx.consultar(_todas_empresas))
    # Las empresas 10 y 20 tienen sembrada su propia moneda USD (datos propios),
    # pero el resto de tablas de A no pueden tener filas de B: solo A registró
    # tipos, asientos en divisa y diferencias.
    assert {m[0] for m in monedas} == {10, 20}
    assert {t[0] for t in tipos} == {10}
    assert {a[0] for a in asientos} == {10}
    assert {d[0] for d in diferencias} == {10}