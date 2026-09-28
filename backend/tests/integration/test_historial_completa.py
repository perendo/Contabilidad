"""Integración US3 completa (SPEC-016 T041).

Tras postear un asiento en divisa, el tipo aparece sellado en el histórico y no
se puede modificar (API y DB); la consulta por asiento devuelve el mismo ratio.
"""

from __future__ import annotations

import uuid as _uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.monedas.tipo_cambio import TipoCambio


def test_tipo_sellado_tras_poster_y_consulta_por_asiento(forex_client):
    fx = forex_client
    tipo = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    assert tipo.status_code == 201
    tipo_id = tipo.json()["id"]

    resp = fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    assert resp.status_code == 201
    asiento_id = resp.json()["asiento_id"]

    # 1. El tipo quedó sellado en el histórico de la empresa
    todos = fx.get(10, "/api/v1/tipos-cambio")
    assert todos.json()["total"] == 1
    assert todos.json()["items"][0]["sellado"] is True
    assert todos.json()["items"][0]["usos_posteados"] == 1

    # 2. La consulta por asiento devuelve el mismo ratio sellado
    historial = fx.get(10, "/api/v1/tipos-cambio/historial", asiento_id=asiento_id)
    assert historial.json()["items"][0]["ratio"] == "1.08500000"
    assert historial.json()["items"][0]["sellado"] is True

    # 3. Modificación -> 409 por API
    patch = fx.patch(f"/api/v1/tipos-cambio/{tipo_id}", empresa_id=10,
                     json={"ratio": "1.20000000", "motivo": "intento"})
    assert patch.status_code == 409

    # 4. Modificación directa en la DB -> rechazada por trigger (integridad)
    async def _alterar(session):
        fila = await session.scalar(
            select(TipoCambio).where(TipoCambio.empresa_id == 10)
        )
        assert fila is not None
        assert fila.sellado  # el trigger exige sellado = (usos > 0)
        fila.ratio = Decimal("2.00000000")
        await session.flush()

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_alterar))

    # 5. Delete directo en la DB también bloqueado
    async def _borrar(session):
        await session.execute(
            text("DELETE FROM tipo_cambio WHERE id = :id"),
            {"id": _uuid.UUID(tipo_id).hex},
        )

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_borrar))