"""Full cross-company tenant isolation (T052).

Scenario: remesa in company A, devolución in company B. From B, A's remesa,
its recibo liquidation and its cobro all answer 404; lists never leak between
companies (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.recibo_remesa import ReciboRemesa


async def _vencimiento(db_session_factory, empresa_id: int, recibo_num: str) -> str:
    async with db_session_factory() as session:
        vencimiento = Vencimiento(
            empresa_id=empresa_id,
            tercero_id=uuid.uuid4(),
            factura_id=None,
            recibo_num=recibo_num,
            iban="ES9121000418450200051332",
            ejercicio=2026,
            fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=10),
            importe=Decimal("100.0000"),
            estado=EstadoVencimiento.pendiente,
        )
        session.add(vencimiento)
        await session.flush()
        vencimiento_id = str(vencimiento.id)
        await session.commit()
    return vencimiento_id


async def _flujo_remesa_cobrada(client, db_session_factory) -> dict[str, str]:
    test_client, state, _ = client
    vencimiento_id = await _vencimiento(db_session_factory, state["empresa_id"], "R-ISO")
    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "SEPA_DD", "tipo_adeudo": "CORE", "recibo_ids": [vencimiento_id]},
    )
    assert creada.status_code == 201
    remesa_id = creada.json()["id"]
    async with db_session_factory() as session:
        recibo_id = str(
            (
                await session.scalars(
                    select(ReciboRemesa.id).where(
                        ReciboRemesa.empresa_id == state["empresa_id"],
                        ReciboRemesa.remesa_id == uuid.UUID(remesa_id),
                    )
                )
            ).one()
        )
    assert test_client.post(f"/api/v1/remesas/{remesa_id}/emitir").status_code == 200
    assert (
        test_client.post(
            f"/api/v1/remesas/{remesa_id}/recibos/{recibo_id}/cobrar"
        ).status_code
        == 200
    )
    return {"remesa_id": remesa_id, "recibo_id": recibo_id}


async def test_cross_empresa_remesa_y_devolucion_aisladas(client, db_session_factory):
    test_client, state, _ = client

    state["empresa_id"] = 42
    flujo_a = await _flujo_remesa_cobrada(client, db_session_factory)

    state["empresa_id"] = 43
    flujo_b = await _flujo_remesa_cobrada(client, db_session_factory)
    importada = test_client.post(
        "/api/v1/devoluciones/import",
        json={
            "devoluciones": [
                {
                    "recibo_id": flujo_b["recibo_id"],
                    "codigo": "MD06",
                    "motivo": "mandato rechazado",
                    "importe": "100.0000",
                    "importe_gastos": "5.0000",
                    "fecha_registro": "2026-10-05",
                }
            ]
        },
    )
    assert importada.status_code == 200
    assert importada.json()["procesadas"] == 1
    devolucion_id = None
    async with db_session_factory() as session:
        from models.treasury.devolucion import DevolucionRecibo

        devolucion_id = str(
            (
                await session.scalars(
                    select(DevolucionRecibo.id).where(
                        DevolucionRecibo.empresa_id == 43
                    )
                )
            ).one()
        )

    # Desde B: los recursos de A son invisibles
    assert (
        test_client.get(f"/api/v1/remesas/{flujo_a['remesa_id']}").status_code == 404
    )
    assert (
        test_client.post(
            f"/api/v1/remesas/{flujo_a['remesa_id']}/recibos/{flujo_a['recibo_id']}/cobrar"
        ).status_code
        == 404
    )
    assert (
        test_client.post(
            f"/api/v1/recibos/{flujo_a['recibo_id']}/liquidar",
            json={"fecha_pago": "2026-10-05"},
        ).status_code
        == 404
    )

    lista_remesas_b = test_client.get("/api/v1/remesas").json()
    assert lista_remesas_b["total"] == 1
    assert lista_remesas_b["items"][0]["id"] == flujo_b["remesa_id"]
    lista_dev_b = test_client.get("/api/v1/devoluciones").json()
    assert [d["id"] for d in lista_dev_b["items"]] == [devolucion_id]

    # Desde A: el activo de B es invisible
    state["empresa_id"] = 42
    assert test_client.get(f"/api/v1/devoluciones/{devolucion_id}").status_code == 404
    lista_remesas_a = test_client.get("/api/v1/remesas").json()
    assert lista_remesas_a["total"] == 1
    assert lista_remesas_a["items"][0]["id"] == flujo_a["remesa_id"]
    lista_dev_a = test_client.get("/api/v1/devoluciones").json()
    assert lista_dev_a["items"] == []

    state["empresa_id"] = 42