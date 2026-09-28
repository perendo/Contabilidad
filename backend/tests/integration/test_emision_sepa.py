"""SEPA PAIN.008.001.02 emission integration tests (T027).

FR-003/FR-004/FR-009: create + emit a remesa; the generated document is parsed
against the PAIN.008 structure and the totals, deadlines and states must match.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from xml.etree import ElementTree

import pytest
from sqlalchemy import select

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.mandato_sepa import MandatoEstado, MandatoSepa
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance.emision import (
    MandatoB2BError,
    PlazoPresentacionRemesaError,
    crear_remesa,
    emitir_remesa,
)
from services.remittance.seleccion import Emisor

NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
EMISOR = Emisor(
    nombre="ACME SL",
    nif="B12345678",
    iban="ES9121000418450200051332",
    bic="CAIXESBBXXX",
)


def _tag(nombre: str) -> str:
    return f"{{{NS}}}{nombre}"


async def _vencimiento(session, *, tipo: str = "", importe: str = "150.0000") -> Vencimiento:
    vencimiento = Vencimiento(
        empresa_id=9,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num=f"R-{uuid.uuid4().hex[:8]}",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=date(2026, 10, 10),
        importe=Decimal(importe),
        estado=EstadoVencimiento.pendiente,
    )
    session.add(vencimiento)
    await session.flush()
    if tipo:
        session.add(
            MandatoSepa(
                empresa_id=9,
                tercero_id=vencimiento.tercero_id,
                mandato_ref=f"MAND-{vencimiento.tercero_id.hex[:6]}",
                fecha_firma=date(2026, 1, 15),
                tipo=tipo,
                estado=MandatoEstado.firmado,
            )
        )
        await session.flush()
    return vencimiento


async def test_crear_y_emitir_sepa_genera_fichero_valido(db_session):
    v1 = await _vencimiento(db_session, tipo="CORE", importe="150.0000")
    v2 = await _vencimiento(db_session, tipo="CORE", importe="300.0000")
    remesa = await crear_remesa(
        db_session,
        9,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[v1.id, v2.id],
    )

    remesa, blob, contenido = await emitir_remesa(
        db_session, 9, remesa.id, emisor=EMISOR
    )
    await db_session.commit()

    assert blob.empresa_id == 9
    assert blob.tipo.value == "remesa_sepa"
    assert blob.sha256 == hashlib.sha256(contenido).hexdigest()
    assert remesa.estado.value == "emitida"
    assert remesa.fecha_emision is not None
    assert remesa.fichero_id == blob.id

    recibos = list(
        (
            await db_session.scalars(
                select(ReciboRemesa).where(
                    ReciboRemesa.empresa_id == 9, ReciboRemesa.remesa_id == remesa.id
                )
            )
        ).all()
    )
    assert all(r.estado.value == "remesado" for r in recibos)

    root = ElementTree.fromstring(contenido)
    grupo = root.find(_tag("CstmrDrctDbtInitn"))
    cabecera = grupo.find(_tag("GrpHdr"))
    assert cabecera.find(_tag("NbOfTxs")).text == "2"
    assert cabecera.find(_tag("CtrlSum")).text == "450.00"
    assert cabecera.find(_tag("MsgId")).text == f"REM-009-{remesa.numero_remesa:06d}"

    pmt_inf = grupo.findall(_tag("PmtInf"))
    assert len(pmt_inf) == 1
    inf = pmt_inf[0]
    assert inf.find(_tag("PmtMtd")).text == "DD"
    assert inf.find(_tag("ReqdColltnDt")).text == "2026-10-10"
    assert inf.find(f"{_tag('PmtTpInf')}/{_tag('SvcLvl')}/{_tag('Cd')}").text == "SEPA"
    assert inf.find(f"{_tag('PmtTpInf')}/{_tag('LclInstrm')}/{_tag('Cd')}").text == "CORE"
    assert inf.find(f"{_tag('CdtrAcct')}/{_tag('Id')}/{_tag('IBAN')}").text == EMISOR.iban

    instrucciones = inf.findall(_tag("DrctDbtTxInf"))
    assert len(instrucciones) == 2
    importes = sorted(
        instr.find(_tag("InstdAmt")).text for instr in instrucciones
    )
    assert importes == ["150.00", "300.00"]
    adeudos = {i: instr.find(_tag("PmtId")).find(_tag("EndToEndId")).text for i, instr in enumerate(instrucciones)}
    assert set(adeudos.values()) == {v1.recibo_num, v2.recibo_num}
    assert all(
        instr.find(f"{_tag('DrctDbtTx')}/{_tag('MndtRltdInf')}") is not None
        for instr in instrucciones
    )


async def test_b2b_sin_mandato_firmado_rechazado(db_session):
    v = await _vencimiento(db_session)  # sin mandato
    remesa = await crear_remesa(
        db_session, 9, formato="SEPA_DD", tipo_adeudo="B2B", vencimiento_ids=[v.id]
    )
    with pytest.raises(MandatoB2BError):
        await emitir_remesa(db_session, 9, remesa.id, emisor=EMISOR)


async def test_b2b_con_mandato_firmado_emite(db_session):
    v = await _vencimiento(db_session, tipo="B2B")
    remesa = await crear_remesa(
        db_session, 9, formato="SEPA_DD", tipo_adeudo="B2B", vencimiento_ids=[v.id]
    )
    remesa, blob, contenido = await emitir_remesa(
        db_session, 9, remesa.id, emisor=EMISOR
    )
    root = ElementTree.fromstring(contenido)
    inf = root.find(f"{_tag('CstmrDrctDbtInitn')}/{_tag('PmtInf')}")
    assert inf.find(f"{_tag('PmtTpInf')}/{_tag('LclInstrm')}/{_tag('Cd')}").text == "B2B"
    assert blob.sha256 == hashlib.sha256(contenido).hexdigest()


async def test_plazo_core_d2_violado_rechazado(db_session):
    vencimiento = Vencimiento(
        empresa_id=9,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="R-PLAZO",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=1),
        importe=Decimal("150.0000"),
        estado=EstadoVencimiento.pendiente,
    )
    db_session.add(vencimiento)
    await db_session.flush()
    remesa = await crear_remesa(
        db_session, 9, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[vencimiento.id]
    )
    with pytest.raises(PlazoPresentacionRemesaError):
        await emitir_remesa(db_session, 9, remesa.id, emisor=EMISOR)


async def test_emision_no_se_repite(db_session):
    v = await _vencimiento(db_session)
    remesa = await crear_remesa(
        db_session, 9, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v.id]
    )
    await emitir_remesa(db_session, 9, remesa.id, emisor=EMISOR)
    from services.remittance.emision import EmisionEstadoError

    with pytest.raises(EmisionEstadoError):
        await emitir_remesa(db_session, 9, remesa.id, emisor=EMISOR)