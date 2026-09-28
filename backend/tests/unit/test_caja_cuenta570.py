"""Reglas de la subcuenta 570 y del ciclo de la caja (SPEC-019 US3).

La caja solo puede usar una subcuenta 570 existente, apuntable y no asignada a
otra caja; los nombres son únicos por empresa; una caja inactiva no admite
movimientos.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from services.ngo.caja import crear_caja, inactivar_caja, registrar_movimiento
from services.ngo.errores import NgoError


def _cuenta_id(ns, empresa_id, code):
    from sqlalchemy import select

    from models.acct.account_plan import AccountPlan

    async def _op(session):
        return await session.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
            )
        )

    return ns.run(ns.consultar(_op))


def _crear(ns, empresa_id, nombre, cuenta=None):
    cuenta_570_id = cuenta if cuenta is not None else ns.subcuenta_570(empresa_id)
    return ns.run(
        ns.mutar(
            lambda s: crear_caja(
                s,
                empresa_id=empresa_id,
                nombre=nombre,
                cuenta_570_id=cuenta_570_id,
                tipo="caja",
            )
        )
    )


def test_cuenta_570_rechazada(ngo_client):
    ns = ngo_client
    banco = _cuenta_id(ns, 10, "5720")
    with pytest.raises(NgoError) as exc:
        _crear(ns, 10, "Caja mala", banco)
    assert exc.value.code == "cuenta_570_no_encontrada"

    padre570 = _cuenta_id(ns, 10, "570")
    with pytest.raises(NgoError) as exc2:
        _crear(ns, 10, "Caja apuntable", padre570)
    assert exc2.value.code == "cuenta_570_no_apuntable"


def test_nombre_duplicado_y_aislamiento(ngo_client):
    ns = ngo_client
    _crear(ns, 10, "Caja principal")
    with pytest.raises(NgoError) as exc:
        _crear(ns, 10, "Caja principal")
    assert exc.value.code == "nombre_duplicado"

    _crear(ns, 20, "Caja principal")


def test_caja_inactiva_no_admite_movimientos(ngo_client):
    ns = ngo_client
    caja = _crear(ns, 10, "Caja a inactivar")
    sid = uuid.UUID(caja["id"])

    async def _op(session):
        await inactivar_caja(session, empresa_id=10, caja_id=sid)

    ns.run(ns.mutar(_op))

    contrapartida = _cuenta_id(ns, 10, "1110")
    with pytest.raises(NgoError) as exc:
        ns.run(
            ns.mutar(
                lambda s: registrar_movimiento(
                    s,
                    empresa_id=10,
                    caja_id=sid,
                    tipo="entrada",
                    importe=Decimal("100.0000"),
                    fecha=date(2026, 8, 1),
                    concepto="Mov",
                    contrapartida_cuenta_id=contrapartida,
                )
            )
        )
    assert exc.value.code == "caja_inactiva"