"""Complete devolution flow tests (T048, T049a).

Importar un R19/C19 genera DevolucionRecibo + asiento REVERSAL balanceado
(430 + 626 si gastos | 572), reabre el vencimiento y marca el recibo devuelto
sin tocar el asiento original; reprocesados rechazados; códigos de hasta 4
caracteres aceptados.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.devolucion import DevolucionRecibo
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa

TERCERO = str(uuid.uuid4())


async def _vencimiento(db_session_factory) -> tuple[str, str]:
    async with db_session_factory() as session:
        vencimiento = Vencimiento(
            empresa_id=42,
            tercero_id=uuid.UUID(TERCERO),
            factura_id=None,
            recibo_num="R-DEV",
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
    return vencimiento_id, TERCERO


async def _recibo_cobrado_via_api(client, db_session_factory) -> dict[str, str]:
    test_client, _, _ = client
    vencimiento_id, _ = await _vencimiento(db_session_factory)
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
                        ReciboRemesa.empresa_id == 42,
                        ReciboRemesa.remesa_id == uuid.UUID(remesa_id),
                    )
                )
            ).one()
        )
    assert test_client.post(f"/api/v1/remesas/{remesa_id}/emitir").status_code == 200
    cobrado = test_client.post(f"/api/v1/remesas/{remesa_id}/recibos/{recibo_id}/cobrar")
    assert cobrado.status_code == 200
    return {"recibo_id": recibo_id, "remesa_id": remesa_id, "vencimiento_id": vencimiento_id}


def _body_devolucion(recibo_id: str, **extra) -> dict:
    cuerpo = {
        "recibo_id": recibo_id,
        "codigo": "R19",
        "motivo": "MD06 - Mandato rechazado",
        "importe": "100.0000",
        "fecha_registro": "2026-10-05",
        **extra,
    }
    return {"devoluciones": [cuerpo]}


async def test_importar_devolucion_con_gastos(client, db_session_factory):
    test_client, _, _ = client
    ids = await _recibo_cobrado_via_api(client, db_session_factory)

    respuesta = test_client.post(
        "/api/v1/devoluciones/import",
        json=_body_devolucion(
            ids["recibo_id"], importe_gastos="5.0000", codigo="MD06"
        ),
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["procesadas"] == 1
    assert cuerpo["rechazadas"] == []
    assert cuerpo["total"] == 1

    async with db_session_factory() as session:
        recibo = await session.scalar(
            select(ReciboRemesa).where(ReciboRemesa.id == uuid.UUID(ids["recibo_id"]))
        )
        assert recibo.estado == ReciboEstado.devuelto

        vencimiento = await session.scalar(
            select(Vencimiento).where(
                Vencimiento.id == uuid.UUID(ids["vencimiento_id"])
            )
        )
        assert vencimiento.estado == EstadoVencimiento.pendiente

        devolucion = await session.scalar(
            select(DevolucionRecibo).where(
                DevolucionRecibo.empresa_id == 42,
                DevolucionRecibo.recibo_remesa_id == recibo.id,
            )
        )
        assert devolucion is not None
        assert devolucion.codigo == "MD06"
        assert devolucion.importe_gastos == Decimal("5.0000")

        asiento = await session.scalar(
            select(JournalEntry).where(JournalEntry.id == devolucion.asiento_reversal_id)
        )
        assert asiento.tipo == JournalEntryTipo.REVERSAL
        assert asiento.original_id == recibo.asiento_cobro_id
        lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id == asiento.id
                    )
                )
            ).all()
        )
        debe = sum((l.debe for l in lineas), Decimal(0))
        haber = sum((l.haber for l in lineas), Decimal(0))
        assert debe == haber == Decimal("105.0000")
        assert {l.cuenta for l in lineas if l.debe > 0} == {"430", "626"}
        assert {l.cuenta for l in lineas if l.haber > 0} == {"572"}

        original = await session.scalar(
            select(JournalEntry).where(JournalEntry.id == recibo.asiento_cobro_id)
        )
        assert original.tipo == JournalEntryTipo.COBRO
        original_lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id == original.id
                    )
                )
            ).all()
        )
        assert len(original_lineas) == 2
        assert sum((l.debe for l in original_lineas), Decimal(0)) == Decimal("100.0000")


async def test_importar_devolucion_sin_gastos_codigo_4_caracteres(client, db_session_factory):
    test_client, _, _ = client
    ids = await _recibo_cobrado_via_api(client, db_session_factory)

    respuesta = test_client.post(
        "/api/v1/devoluciones/import",
        json=_body_devolucion(
            ids["recibo_id"], codigo="AC04", motivo="IBAN inválido", tipo="C19"
        ),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["procesadas"] == 1

    async with db_session_factory() as session:
        devolucion = await session.scalar(
            select(DevolucionRecibo).where(DevolucionRecibo.codigo == "AC04")
        )
        assert devolucion is not None
        assert devolucion.identificador_externo.startswith("C19:AC04:")
        asiento = await session.scalar(
            select(JournalEntry).where(JournalEntry.id == devolucion.asiento_reversal_id)
        )
        lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id == asiento.id
                    )
                )
            ).all()
        )
        assert sum((l.debe for l in lineas), Decimal(0)) == sum((l.haber for l in lineas), Decimal(0))
        assert {l.cuenta for l in lineas if l.debe > 0} == {"430"}
        assert {l.cuenta for l in lineas if l.haber > 0} == {"572"}


async def test_reprocesado_del_mismo_retorno_rechazado(client, db_session_factory):
    test_client, _, _ = client
    ids = await _recibo_cobrado_via_api(client, db_session_factory)

    primera = test_client.post(
        "/api/v1/devoluciones/import",
        json=_body_devolucion(ids["recibo_id"], codigo="R-CUST"),
    )
    assert primera.status_code == 200
    assert primera.json()["procesadas"] == 1

    segunda = test_client.post(
        "/api/v1/devoluciones/import",
        json=_body_devolucion(ids["recibo_id"], codigo="R-CUST"),
    )
    assert segunda.status_code == 200
    cuerpo = segunda.json()
    assert cuerpo["procesadas"] == 0
    assert cuerpo["rechazadas"][0]["code"] == "retorno_ya_procesado"

    async with db_session_factory() as session:
        n_asientos_reversal = (
            await session.scalars(
                select(JournalEntry.id).where(
                    JournalEntry.empresa_id == 42,
                    JournalEntry.tipo == JournalEntryTipo.REVERSAL,
                )
            )
        ).all()
        assert len(n_asientos_reversal) == 1


async def test_devolucion_de_recibo_no_cobrado_rechazada(client, db_session_factory):
    test_client, _, _ = client
    vencimiento_id, _ = await _vencimiento(db_session_factory)
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
                        ReciboRemesa.empresa_id == 42,
                        ReciboRemesa.remesa_id == uuid.UUID(remesa_id),
                    )
                )
            ).one()
        )

    respuesta = test_client.post(
        "/api/v1/devoluciones/import",
        json=_body_devolucion(recibo_id),
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["procesadas"] == 0
    assert cuerpo["rechazadas"][0]["code"] == "recibo_no_cobrado"


def _fichero_r19(recibo_num: str, codigo: str, motivo: str, importe_cents: str) -> bytes:
    cuerpo = (
        "1ACME SA                                       20261001"
        "0000000100000000000100000000000000000000000000000000"
        "00000000000000000000000000000000000000000000000000  \r\n"
    )
    linea3 = (
        "3"
        + codigo.ljust(10)
        + "RV"
        + recibo_num.ljust(12)
        + "20261005"
        + importe_cents.rjust(12, "0")
        + "000000000000"
        + motivo.ljust(40)
    )
    return (cuerpo + linea3 + "\r\n").encode("ISO-8859-15")


async def test_importar_fichero_r19_multipart(client, db_session_factory):
    test_client, _, _ = client
    ids = await _recibo_cobrado_via_api(client, db_session_factory)

    recibo_no = None
    async with db_session_factory() as session:
        recibo = await session.scalar(
            select(ReciboRemesa).where(ReciboRemesa.id == uuid.UUID(ids["recibo_id"]))
        )
        recibo_no = recibo.recibo_num

    fichero = _fichero_r19(recibo_no, "MD01", "Referencia no encontrada", "10000")
    respuesta = test_client.post(
        "/api/v1/devoluciones/import",
        files={"file": ("retorno.19", fichero, "text/plain")},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["procesadas"] == 1
    assert cuerpo["rechazadas"] == []

    async with db_session_factory() as session:
        recibo = await session.scalar(
            select(ReciboRemesa).where(ReciboRemesa.id == uuid.UUID(ids["recibo_id"]))
        )
        assert recibo.estado == ReciboEstado.devuelto
        vencimiento = await session.scalar(
            select(Vencimiento).where(Vencimiento.id == uuid.UUID(ids["vencimiento_id"]))
        )
        assert vencimiento.estado == EstadoVencimiento.pendiente
