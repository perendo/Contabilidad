"""Closed-exercise validation (T055).

FR-008 / SPEC-002/004: neither a remesa nor a devolución may be created when
the receivable belongs to a closed exercise. The API answers 409 with code
`ejercicio_cerrado` for remesas; the devolución import rejects the item with
the same code and never creates a REVERSAL (constituciones I-II).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa


async def _vencimiento(
    db_session_factory,
    *,
    ejercicio: int,
    fecha_vencimiento: date,
    recibo_num: str,
) -> str:
    async with db_session_factory() as session:
        vencimiento = Vencimiento(
            empresa_id=42,
            tercero_id=uuid.uuid4(),
            factura_id=None,
            recibo_num=recibo_num,
            iban="ES9121000418450200051332",
            ejercicio=ejercicio,
            fecha_vencimiento=fecha_vencimiento,
            importe=Decimal("100.0000"),
            estado=EstadoVencimiento.pendiente,
        )
        session.add(vencimiento)
        await session.flush()
        vencimiento_id = str(vencimiento.id)
        await session.commit()
    return vencimiento_id


async def test_remesa_ejercicio_cerrado_rechaza_409(client, db_session_factory):
    test_client, _, auth = client
    hh = auth["hh"]
    vencimiento_id = await _vencimiento(
        db_session_factory,
        ejercicio=2024,
        fecha_vencimiento=date(2024, 10, 10),
        recibo_num="R-CERRADO-01",
    )

    respuesta = test_client.post(
        "/api/v1/remesas",
        json={"formato": "SEPA_DD", "tipo_adeudo": "CORE", "recibo_ids": [vencimiento_id]},
        headers=hh(42),
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "ejercicio_cerrado"

    lista = test_client.get("/api/v1/remesas", headers=hh(42))
    assert lista.json()["total"] == 0


async def test_devolucion_ejercicio_cerrado_rechazada(client, db_session_factory):
    test_client, _, auth = client
    hh = auth["hh"]
    vencimiento_id = await _vencimiento(
        db_session_factory,
        ejercicio=2026,
        fecha_vencimiento=date(2024, 10, 10),
        recibo_num="R-CERRADO-02",
    )

    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "CSB_19_19", "tipo_adeudo": "CORE", "recibo_ids": [vencimiento_id]},
        headers=hh(42),
    )
    assert creada.status_code == 201
    remesa_id = creada.json()["id"]
    assert test_client.post(f"/api/v1/remesas/{remesa_id}/emitir", headers=hh(42)).status_code == 200

    async with db_session_factory() as session:
        recibo_id = str(
            (
                await session.scalars(
                    select(ReciboRemesa.id).where(
                        ReciboRemesa.empresa_id == 42,
                        ReciboRemesa.remesa_id == uuid.UUID(remesa_id),
                    )
                )
            ).one()
        )
    cobrado = test_client.post(f"/api/v1/remesas/{remesa_id}/recibos/{recibo_id}/cobrar", headers=hh(42))
    assert cobrado.status_code == 200

    importada = test_client.post(
        "/api/v1/devoluciones/import",
        json={
            "devoluciones": [
                {
                    "recibo_id": recibo_id,
                    "codigo": "MD06",
                    "motivo": "mandato rechazado",
                    "importe": "100.0000",
                    "fecha_registro": "2026-10-05",
                }
            ]
        },
        headers=hh(42),
    )
    assert importada.status_code == 200
    cuerpo = importada.json()
    assert cuerpo["procesadas"] == 0
    assert cuerpo["rechazadas"][0]["code"] == "ejercicio_cerrado"

    async with db_session_factory() as session:
        recibo = await session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == 42,
                ReciboRemesa.id == uuid.UUID(recibo_id),
            )
        )
        assert recibo.estado == ReciboEstado.cobrado
        original = await session.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == 42,
                JournalEntry.tipo == JournalEntryTipo.COBRO,
            )
        )
        assert original is not None
        reversales = (
            await session.scalars(
                select(JournalEntry.id).where(
                    JournalEntry.empresa_id == 42,
                    JournalEntry.tipo == JournalEntryTipo.REVERSAL,
                )
            )
        ).all()
        assert len(reversales) == 0