"""Saldo y movimientos de caja (SPEC-019 US3).

El saldo es la suma Debe-Haber POSTED sobre la subcuenta 570 asignada; cada
entrada/salida genera un asiento balanceado del motor y una traza inmutable
`movimiento_caja`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from services.ngo.caja import (
    crear_caja,
    listar_movimientos,
    registrar_movimiento,
    saldo_570,
)


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


def _crear_caja(ns, empresa_id=10, nombre="Caja general"):
    cuenta_570_id = ns.subcuenta_570(empresa_id)
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


def _movimiento(ns, caja_id, tipo, importe, contrapartida, fecha="2026-08-01"):
    return ns.run(
        ns.mutar(
            lambda s: registrar_movimiento(
                s,
                empresa_id=10,
                caja_id=caja_id,
                tipo=tipo,
                importe=Decimal(importe),
                fecha=date.fromisoformat(fecha),
                concepto="Movimiento",
                contrapartida_cuenta_id=contrapartida,
            )
        )
    )


def test_saldo_acumula_movimientos(ngo_client):
    ns = ngo_client
    caja = _crear_caja(ns, 10)
    sid = uuid.UUID(caja["id"])
    capital = _cuenta_id(ns, 10, "1110")
    banco = _cuenta_id(ns, 10, "5720")

    assert caja["saldo"] == "0.0000"
    entrada = _movimiento(ns, sid, "entrada", "500.0000", capital)
    assert entrada["tipo"] == "entrada"
    assert entrada["saldo"] == "500.0000"

    salida = _movimiento(ns, sid, "salida", "300.0000", banco, "2026-08-02")
    assert salida["saldo"] == "200.0000"

    c570 = ns.subcuenta_570(10)
    saldo = ns.run(ns.consultar(lambda s: saldo_570(s, empresa_id=10, account_id=c570)))
    assert saldo == Decimal("200.0000")

    listado = ns.run(ns.mutar(lambda s: listar_movimientos(s, empresa_id=10, caja_id=sid)))
    assert listado["total"] == 2


def test_saldo_respeto_hasta(ngo_client):
    ns = ngo_client
    caja = _crear_caja(ns, 10)
    sid = uuid.UUID(caja["id"])
    capital = _cuenta_id(ns, 10, "1110")
    _movimiento(ns, sid, "entrada", "700.0000", capital, "2026-08-01")
    _movimiento(ns, sid, "salida", "200.0000", capital, "2026-08-03")

    c570 = ns.subcuenta_570(10)
    s1 = ns.run(
        ns.consultar(
            lambda s: saldo_570(
                s, empresa_id=10, account_id=c570, hasta=date(2026, 8, 2)
            )
        )
    )
    assert s1 == Decimal("700.0000")
    s2 = ns.run(
        ns.consultar(
            lambda s: saldo_570(
                s, empresa_id=10, account_id=c570, hasta=date(2026, 8, 31)
            )
        )
    )
    assert s2 == Decimal("500.0000")