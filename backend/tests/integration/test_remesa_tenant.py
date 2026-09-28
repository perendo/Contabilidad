"""Cross-tenant isolation for US1 API flow (T029).

Company A creates and emits a remesa; company B cannot see it in list/detail/
file and cannot collect any of its receivables (silent 404, constitución III).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.recibo_remesa import ReciboRemesa


async def _preparar_remesa_emitida(client, db_session_factory):
    test_client, _, auth = client
    hh = auth["hh"]
    async with db_session_factory() as session:
        vencimiento = Vencimiento(
            empresa_id=42,
            tercero_id=uuid.uuid4(),
            factura_id=None,
            recibo_num="R-TENANT",
            iban="ES9121000418450200051332",
            ejercicio=2026,
            fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=10),
            importe=Decimal("150.0000"),
            estado=EstadoVencimiento.pendiente,
        )
        session.add(vencimiento)
        await session.commit()
        vencimiento_id = vencimiento.id

    creado = test_client.post(
        "/api/v1/remesas",
        json={
            "formato": "SEPA_DD",
            "tipo_adeudo": "CORE",
            "recibo_ids": [str(vencimiento_id)],
        },
        headers=hh(42),
    )
    assert creado.status_code == 201
    remesa_id = creado.json()["id"]
    emitido = test_client.post(f"/api/v1/remesas/{remesa_id}/emitir", headers=hh(42))
    assert emitido.status_code == 200
    return remesa_id, vencimiento_id


async def test_empresa_b_no_ve_remesa_ni_recibos(client, db_session_factory):
    remesa_id, vencimiento_id = await _preparar_remesa_emitida(
        client, db_session_factory
    )
    test_client, _, auth = client
    hh = auth["hh"]

    listado = test_client.get("/api/v1/remesas", headers=hh(42))
    assert listado.json()["total"] == 1

    assert test_client.get("/api/v1/remesas", headers=hh(43)).json()["total"] == 0
    assert test_client.get(f"/api/v1/remesas/{remesa_id}", headers=hh(43)).status_code == 404
    assert test_client.get(f"/api/v1/remesas/{remesa_id}/fichero", headers=hh(43)).status_code == 404

    async with db_session_factory() as session:
        recibo = await session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == 42,
                ReciboRemesa.vencimiento_id == vencimiento_id,
            )
        )
    assert recibo is not None
    cobro = test_client.post(f"/api/v1/remesas/{remesa_id}/recibos/{recibo.id}/cobrar", headers=hh(43))
    assert cobro.status_code == 404


async def test_empresa_a_ve_su_remesa_y_cobra(client, db_session_factory):
    remesa_id, _ = await _preparar_remesa_emitida(client, db_session_factory)
    test_client, _, auth = client
    hh = auth["hh"]

    detalle = test_client.get(f"/api/v1/remesas/{remesa_id}", headers=hh(42))
    assert detalle.status_code == 200
    assert detalle.json()["n_recibos"] == 1
    recibo_id = detalle.json()["recibos"][0]["id"]
    cobro = test_client.post(f"/api/v1/remesas/{remesa_id}/recibos/{recibo_id}/cobrar", headers=hh(42))
    assert cobro.status_code == 200
    assert cobro.json()["recibo"]["estado"] == "cobrado"