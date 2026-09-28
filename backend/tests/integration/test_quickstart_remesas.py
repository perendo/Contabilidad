"""Quickstart scenarios reproduction (T053).

Re-produces the six Scenarios of specs/020-remesas-sepa-cobros/quickstart.md
against the treasury API and verifies the expected outcomes.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

from sqlalchemy import select

from models.acct.journal import JournalEntryLine
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.devolucion import DevolucionRecibo
from models.treasury.recibo_remesa import ReciboRemesa

NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
EMPRESA = 52


def _tag(nombre: str) -> str:
    return f"{{{NS}}}{nombre}"


async def _vencimiento(db_session_factory, importe="150.0000", recibo_num=None, tercero=None):
    async with db_session_factory() as session:
        vencimiento = Vencimiento(
            empresa_id=EMPRESA,
            tercero_id=tercero or uuid.uuid4(),
            factura_id=None,
            recibo_num=recibo_num or f"R-{uuid.uuid4().hex[:8]}",
            iban="ES9121000418450200051332",
            ejercicio=2026,
            fecha_vencimiento=date(2026, 10, 10),
            importe=Decimal(importe),
            estado=EstadoVencimiento.pendiente,
        )
        session.add(vencimiento)
        await session.flush()
        vencimiento_id = str(vencimiento.id)
        tercero_id = str(vencimiento.tercero_id)
        await session.commit()
    return vencimiento_id, tercero_id


async def _recibo_id(db_session_factory, remesa_id: str) -> str:
    async with db_session_factory() as session:
        recibo = (
            await session.scalars(
                select(ReciboRemesa).where(
                    ReciboRemesa.empresa_id == EMPRESA,
                    ReciboRemesa.remesa_id == uuid.UUID(remesa_id),
                )
            )
        ).first()
        assert recibo is not None
        return str(recibo.id)


async def test_scenario1_core_cobro_manual(client, db_session_factory):
    test_client, state, _ = client
    state["empresa_id"] = EMPRESA
    v1, _ = await _vencimiento(db_session_factory, importe="150.0000")
    v2, _ = await _vencimiento(db_session_factory, importe="300.0000")

    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "SEPA_DD", "tipo_adeudo": "CORE", "recibo_ids": [v1, v2]},
    )
    assert creada.status_code == 201
    remesa = creada.json()
    assert remesa["numero_remesa"] >= 1
    assert remesa["importe_total"] == "450.0000"
    assert remesa["n_recibos"] == 2
    remesa_id = remesa["id"]

    emitida = test_client.post(f"/api/v1/remesas/{remesa_id}/emitir")
    assert emitida.status_code == 200
    assert emitida.json()["estado"] == "emitida"
    assert "sha256" in emitida.json()

    fichero = test_client.get(f"/api/v1/remesas/{remesa_id}/fichero")
    assert fichero.status_code == 200
    root = ElementTree.fromstring(fichero.content)
    cabecera = root.find(f"{_tag('CstmrDrctDbtInitn')}/{_tag('GrpHdr')}")
    assert cabecera.find(_tag("NbOfTxs")).text == "2"
    assert cabecera.find(_tag("CtrlSum")).text == "450.00"

    recibo_id = await _recibo_id(db_session_factory, remesa_id)
    cobrado = test_client.post(f"/api/v1/remesas/{remesa_id}/recibos/{recibo_id}/cobrar")
    assert cobrado.status_code == 200
    asiento_id = cobrado.json()["asiento_id"]
    assert asiento_id is not None

    async with db_session_factory() as session:
        recibo = await session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == EMPRESA,
                ReciboRemesa.id == uuid.UUID(recibo_id),
            )
        )
        assert recibo is not None
        lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id == uuid.UUID(asiento_id)
                    )
                )
            ).all()
        )
        debe = sum((l.debe for l in lineas), Decimal(0))
        haber = sum((l.haber for l in lineas), Decimal(0))
        assert debe == haber == recibo.importe


async def test_scenario2_b2b_con_mandato(client, db_session_factory):
    test_client, state, _ = client
    state["empresa_id"] = EMPRESA
    vencimiento_id, tercero_id = await _vencimiento(db_session_factory, importe="100.0000")

    mandato = test_client.post(
        f"/api/v1/terceros/{tercero_id}/mandatos",
        json={"mandato_ref": "MAND-B2B-001", "fecha_firma": "2026-09-15", "tipo": "B2B"},
    )
    assert mandato.status_code == 201

    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "SEPA_DD", "tipo_adeudo": "B2B", "recibo_ids": [vencimiento_id]},
    )
    assert creada.status_code == 201
    remesa_id = creada.json()["id"]
    emitida = test_client.post(f"/api/v1/remesas/{remesa_id}/emitir")
    assert emitida.status_code == 200
    fichero = test_client.get(f"/api/v1/remesas/{remesa_id}/fichero")
    root = ElementTree.fromstring(fichero.content)
    inf = root.find(f"{_tag('CstmrDrctDbtInitn')}/{_tag('PmtInf')}")
    assert inf.find(f"{_tag('PmtTpInf')}/{_tag('LclInstrm')}/{_tag('Cd')}").text == "B2B"
    assert inf.find(f"{_tag('DrctDbtTxInf')}/{_tag('DrctDbtTx')}/{_tag('MndtRltdInf')}") is not None


async def test_scenario3_devolucion_r19_reversal(client, db_session_factory):
    test_client, state, _ = client
    state["empresa_id"] = EMPRESA
    vencimiento_id, _ = await _vencimiento(db_session_factory, importe="150.0000")
    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "SEPA_DD", "tipo_adeudo": "CORE", "recibo_ids": [vencimiento_id]},
    )
    remesa_id = creada.json()["id"]
    test_client.post(f"/api/v1/remesas/{remesa_id}/emitir")
    recibo_id = await _recibo_id(db_session_factory, remesa_id)
    cobrado = test_client.post(f"/api/v1/remesas/{remesa_id}/recibos/{recibo_id}/cobrar")
    asiento_original = cobrado.json()["asiento_id"]

    importada = test_client.post(
        "/api/v1/devoluciones/import",
        json={
            "devoluciones": [
                {
                    "recibo_id": recibo_id,
                    "codigo": "R19",
                    "motivo": "MD06 - Mandato rechazado",
                    "importe": "150.0000",
                    "importe_gastos": "5.0000",
                    "fecha_registro": "2026-10-05",
                }
            ]
        },
    )
    assert importada.status_code == 200
    assert importada.json()["procesadas"] == 1

    async with db_session_factory() as session:
        recibo = await session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == EMPRESA,
                ReciboRemesa.id == uuid.UUID(recibo_id),
            )
        )
        assert recibo.estado.value == "devuelto"
        vencimiento = await session.scalar(
            select(Vencimiento).where(
                Vencimiento.empresa_id == EMPRESA,
                Vencimiento.id == uuid.UUID(vencimiento_id),
            )
        )
        assert vencimiento.estado == EstadoVencimiento.pendiente
        devolucion = await session.scalar(
            select(DevolucionRecibo).where(
                DevolucionRecibo.empresa_id == EMPRESA,
                DevolucionRecibo.recibo_remesa_id == recibo.id,
            )
        )
        lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id
                        == devolucion.asiento_reversal_id
                    )
                )
            ).all()
        )
        assert sum((l.debe for l in lineas), Decimal(0)) == Decimal("155.0000")
        assert sum((l.haber for l in lineas), Decimal(0)) == Decimal("155.0000")
        assert {l.cuenta for l in lineas if l.debe > 0} == {"430", "626"}
        assert {l.cuenta for l in lineas if l.haber > 0} == {"572"}
        original_lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id == uuid.UUID(asiento_original)
                    )
                )
            ).all()
        )
        assert len(original_lineas) == 2
        assert {l.cuenta for l in original_lineas if l.debe > 0} == {"572"}


async def test_scenario4_liquidacion_pronto_pago(client, db_session_factory):
    test_client, state, _ = client
    state["empresa_id"] = EMPRESA
    vencimiento_id, tercero_id = await _vencimiento(db_session_factory, importe="100.0000")

    condicion = test_client.post(
        f"/api/v1/terceros/{tercero_id}/condiciones",
        json={"plazo_dias": 10, "porcentaje": "2.00", "vigente": True},
    )
    assert condicion.status_code == 201

    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "SEPA_DD", "tipo_adeudo": "CORE", "recibo_ids": [vencimiento_id]},
    )
    remesa_id = creada.json()["id"]
    test_client.post(f"/api/v1/remesas/{remesa_id}/emitir")
    recibo_id = await _recibo_id(db_session_factory, remesa_id)

    liquidada = test_client.post(
        f"/api/v1/recibos/{recibo_id}/liquidar",
        json={"fecha_pago": "2026-10-05", "cuenta": "5720000"},
    )
    assert liquidada.status_code == 200
    cuerpo = liquidada.json()
    assert cuerpo["importe_neto"] == "98.0000"
    assert cuerpo["descuento"] == "2.0000"

    async with db_session_factory() as session:
        lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id == uuid.UUID(cuerpo["asiento_id"])
                    )
                )
            ).all()
        )
        assert {l.cuenta for l in lineas if l.debe > 0} == {"5720000", "432"}
        assert {l.cuenta for l in lineas if l.haber > 0} == {"430"}
        assert sum((l.debe for l in lineas), Decimal(0)) == Decimal("100.0000")


async def test_scenario5_csb_1919(client, db_session_factory):
    test_client, state, _ = client
    state["empresa_id"] = EMPRESA
    vencimiento_id, _ = await _vencimiento(db_session_factory, importe="250.0000")
    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "CSB_19_19", "tipo_adeudo": "CORE", "recibo_ids": [vencimiento_id]},
    )
    assert creada.status_code == 201
    remesa_id = creada.json()["id"]
    assert test_client.post(f"/api/v1/remesas/{remesa_id}/emitir").status_code == 200
    fichero = test_client.get(f"/api/v1/remesas/{remesa_id}/fichero")
    assert fichero.status_code == 200
    texto = fichero.content.decode("ISO-8859-15")
    lineas = texto.split("\r\n")
    assert lineas[0][0] == "1"
    assert [l[0] for l in lineas] == ["1", "2", "3", "5"]
    importe_cents = 25000
    assert int(lineas[0][66:78]) == importe_cents
    assert int(lineas[0][78:84]) == 1
    assert int(lineas[2][21:33]) == importe_cents
    assert int(lineas[3][1:13]) == importe_cents
    assert int(lineas[3][19:23]) == importe_cents % 97
    assert all(len(l) == 120 for l in lineas)


async def test_scenario6_aislamiento_multiempresa(client, db_session_factory):
    test_client, state, _ = client
    state["empresa_id"] = EMPRESA
    vencimiento_id, _ = await _vencimiento(db_session_factory, importe="100.0000")
    creada = test_client.post(
        "/api/v1/remesas",
        json={"formato": "SEPA_DD", "tipo_adeudo": "CORE", "recibo_ids": [vencimiento_id]},
    )
    remesa_id = creada.json()["id"]

    state["empresa_id"] = 53
    assert test_client.get(f"/api/v1/remesas/{remesa_id}").status_code == 404
    state["empresa_id"] = EMPRESA