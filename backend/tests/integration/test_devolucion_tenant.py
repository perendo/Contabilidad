"""Tenant isolation for devolutions (T049).

Una devolución creada en la empresa A no es visible para la empresa B, ni en
obtención, ni en detalle. El import no procesa recibos de otra empresa
(recibo no encontrado).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.devolucion import DevolucionRecibo
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import confirmar_cobro, crear_remesa, emitir_remesa
from services.remittance.refund_r19 import procesar_devolucion
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _recibo_cobrado_en(db_session_factory, empresa_id: int, recibo_num: str):
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
        vencimiento_id = vencimiento.id
        remesa = await crear_remesa(
            session,
            empresa_id,
            formato="SEPA_DD",
            tipo_adeudo="CORE",
            vencimiento_ids=[vencimiento_id],
        )
        _, _, _ = await emitir_remesa(session, empresa_id, remesa.id, emisor=EMISOR)
        recibo = await session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == empresa_id,
                ReciboRemesa.remesa_id == remesa.id,
            )
        )
        await confirmar_cobro(
            session, empresa_id, remesa.id, recibo.id, fecha_cobro=date(2026, 10, 5)
        )
        recibo_id = recibo.id
        await session.commit()
    return recibo_id


async def test_devolucion_invisible_entre_empresas(client, db_session_factory):
    test_client, _, auth = client
    hh = auth["hh"]
    recibo_id = await _recibo_cobrado_en(db_session_factory, 42, "R-T602")

    async with db_session_factory() as db:
        devolucion = await procesar_devolucion(
            db,
            42,
            recibo_id=recibo_id,
            codigo="BE04",
            motivo="adendo fallido",
            importe=Decimal("100.0000"),
            fecha_registro=date(2026, 10, 8),
            identificador_externo="R19:BE04:R-T602:2026-10-05:10000:0",
        )
        devolucion_id = str(devolucion.id)
        await db.commit()

    lista = test_client.get("/api/v1/devoluciones", headers=hh(42))
    assert lista.status_code == 200
    ids = [d["id"] for d in lista.json()["items"]]
    assert devolucion_id in ids

    lista_b = test_client.get("/api/v1/devoluciones", headers=hh(43))
    assert lista_b.status_code == 200
    assert devolucion_id not in [d["id"] for d in lista_b.json()["items"]]

    detalle_b = test_client.get(f"/api/v1/devoluciones/{devolucion_id}", headers=hh(43))
    assert detalle_b.status_code == 404


async def test_import_no_procesa_recibo_de_otra_empresa(client, db_session_factory):
    test_client, _, auth = client
    hh = auth["hh"]
    recibo_id = await _recibo_cobrado_en(db_session_factory, 43, "R-TX")

    respuesta = test_client.post(
        "/api/v1/devoluciones/import",
        json={
            "devoluciones": [
                {
                    "recibo_id": str(recibo_id),
                    "codigo": "R19",
                    "motivo": "x",
                    "importe": "100.0000",
                    "fecha_registro": "2026-10-08",
                }
            ]
        },
        headers=hh(42),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["procesadas"] == 0
    assert respuesta.json()["rechazadas"][0]["code"] == "recibo_no_encontrado"

    async with db_session_factory() as db:
        n = (
            await db.scalar(
                select(DevolucionRecibo.id).where(DevolucionRecibo.empresa_id == 42)
            )
            is not None
        )
        assert n is False