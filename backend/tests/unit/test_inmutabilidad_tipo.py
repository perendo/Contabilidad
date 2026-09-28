"""Inmutabilidad del tipo de cambio (SPEC-016 T034).

PATCH/DELETE de un tipo con usos_posteados > 0 -> 409 (API) y violación directa
en la base de datos rechazada por el trigger (constitución II).
"""

from __future__ import annotations

import uuid as _uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.monedas.tipo_cambio import TipoCambio


def test_patch_tipo_sellado_409(forex_client):
    fx = forex_client
    tipo = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    assert tipo.status_code == 201
    tipo_id = tipo.json()["id"]
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")  # sella el tipo

    resp = fx.patch(f"/api/v1/tipos-cambio/{tipo_id}", empresa_id=10,
                    json={"ratio": "1.20000000", "motivo": "intento"})
    assert resp.status_code == 409


def test_patch_tipo_no_sellado_sin_motivo_422(forex_client):
    fx = forex_client
    tipo = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    tipo_id = tipo.json()["id"]
    resp = fx.patch(f"/api/v1/tipos-cambio/{tipo_id}", empresa_id=10,
                    json={"ratio": "1.20000000", "motivo": ""})
    assert resp.status_code == 422


def test_delete_tipo_sellado_rechazado_en_ddbb(forex_client):
    fx = forex_client
    tipo = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    tipo_id = tipo.json()["id"]
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")

    async def _borrar(session):
        await session.execute(
            text("DELETE FROM tipo_cambio WHERE id = :id"),
            {"id": _uuid.UUID(tipo_id).hex},
        )

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_borrar))


def test_update_ratio_sellado_rechazado_en_ddbb(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")

    async def _modificar(session):
        fila = await session.scalar(
            select(TipoCambio).where(TipoCambio.empresa_id == 10)
        )
        assert fila is not None and fila.sellado
        fila.ratio = Decimal("9.00000000")
        await session.flush()

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_modificar))