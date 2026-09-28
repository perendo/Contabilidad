"""Cajas y movimientos por API (SPEC-019 US3 / FR-008).

Alta de caja sobre una subcuenta 570, entrada/salida con asientos del motor,
saldo acumulado, listado, inactivación y 409 al mover una caja inactiva.
"""

from __future__ import annotations


def _cuenta_codigo(ns, empresa_id, code):
    from sqlalchemy import select

    from models.acct.account_plan import AccountPlan

    async def _op(session):
        return await session.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
            )
        )

    return ns.run(ns.consultar(_op))


def test_crear_mover_saldo_y_listar(ngo_client):
    ns = ngo_client
    c570 = ns.subcuenta_570(10)
    capital = _cuenta_codigo(ns, 10, "1110")
    banco = _cuenta_codigo(ns, 10, "5720")

    caja = ns.post(
        "/api/v1/cajas", 10, {"nombre": "Caja principal", "cuenta_570_id": c570, "tipo": "caja"}
    )
    assert caja.status_code == 201, caja.text
    cid = caja.json()["id"]
    assert caja.json()["saldo"] == "0.0000"

    ent = ns.post(
        f"/api/v1/cajas/{cid}/movimientos",
        10,
        {"tipo": "entrada", "importe": "500.0000", "fecha": "2026-08-01", "concepto": "Aportación", "contrapartida_cuenta_id": capital},
    )
    assert ent.status_code == 201, ent.text
    assert ent.json()["saldo"] == "500.0000"

    sal = ns.post(
        f"/api/v1/cajas/{cid}/movimientos",
        10,
        {"tipo": "salida", "importe": "200.0000", "fecha": "2026-08-03", "concepto": "Gasto", "contrapartida_cuenta_id": banco},
    )
    assert sal.status_code == 201
    assert sal.json()["saldo"] == "300.0000"

    detalle = ns.get(10, f"/api/v1/cajas/{cid}")
    assert detalle.status_code == 200
    assert detalle.json()["saldo"] == "300.0000"

    movs = ns.get(10, f"/api/v1/cajas/{cid}/movimientos", fecha_desde="2026-08-02")
    assert movs.json()["total"] == 1
    assert movs.json()["items"][0]["tipo"] == "salida"


def test_inactivar_bloquea_movimientos(ngo_client):
    ns = ngo_client
    c570 = ns.subcuenta_570(10)
    capital = _cuenta_codigo(ns, 10, "1110")
    caja = ns.post(
        "/api/v1/cajas", 10, {"nombre": "Caja chica", "cuenta_570_id": c570, "tipo": "caja_chica"}
    )
    assert caja.status_code == 201, caja.text
    cid = caja.json()["id"]

    ns.post(f"/api/v1/cajas/{cid}/inactivar", 10)
    r = ns.post(
        f"/api/v1/cajas/{cid}/movimientos",
        10,
        {"tipo": "entrada", "importe": "10.0000", "fecha": "2026-08-01", "concepto": "Fondo", "contrapartida_cuenta_id": capital},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "No se pueden registrar movimientos en una caja inactiva"