"""SEPA multi-charge-date grouping tests (T027a).

T023b: one remesa with two charge dates produces two PmtInf blocks with
independent totals and their own ReqdColltnDt.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from xml.etree import ElementTree

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from services.remittance.emision import crear_remesa, emitir_remesa
from services.remittance.seleccion import Emisor

NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


def _tag(nombre: str) -> str:
    return f"{{{NS}}}{nombre}"


def _fecha_futura(dias: int) -> date:
    hoy = datetime.now(timezone.utc).date()
    fecha = hoy
    pendientes = dias
    while pendientes > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            pendientes -= 1
    return fecha


async def _vencimiento(session, empresa_id: int, fecha: date, importe: str) -> Vencimiento:
    vencimiento = Vencimiento(
        empresa_id=empresa_id,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num=f"R-{uuid.uuid4().hex[:8]}",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=fecha,
        importe=Decimal(importe),
        estado=EstadoVencimiento.pendiente,
    )
    session.add(vencimiento)
    await session.flush()
    return vencimiento


async def test_dos_fechas_producen_dos_pmtinf(db_session):
    fecha_a = _fecha_futura(4)
    fecha_b = _fecha_futura(6)
    v1 = await _vencimiento(db_session, 10, fecha_a, "100.0000")
    v2 = await _vencimiento(db_session, 10, fecha_a, "200.0000")
    v3 = await _vencimiento(db_session, 10, fecha_b, "75.0000")

    remesa = await crear_remesa(
        db_session,
        10,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[v1.id, v2.id, v3.id],
    )
    remesa, _blob, contenido = await emitir_remesa(
        db_session, 10, remesa.id, emisor=EMISOR
    )
    await db_session.commit()

    assert remesa.fecha_cargo is None

    root = ElementTree.fromstring(contenido)
    grupo = root.find(_tag("CstmrDrctDbtInitn"))
    bloques = grupo.findall(_tag("PmtInf"))
    assert len(bloques) == 2

    organizado = {}
    for bloque in bloques:
        fecha = bloque.find(_tag("ReqdColltnDt")).text
        importes = sorted(
            i.find(_tag("InstdAmt")).text
            for i in bloque.findall(_tag("DrctDbtTxInf"))
        )
        organizado[fecha] = (bloque, importes)

    assert organizado[fecha_a.isoformat()][1] == ["100.00", "200.00"]
    assert organizado[fecha_b.isoformat()][1] == ["75.00"]
    assert organizado[fecha_a.isoformat()][0].find(_tag("NbOfTxs")).text == "2"
    assert organizado[fecha_a.isoformat()][0].find(_tag("CtrlSum")).text == "300.00"

    cabecera = grupo.find(_tag("GrpHdr"))
    assert cabecera.find(_tag("NbOfTxs")).text == "3"
    assert cabecera.find(_tag("CtrlSum")).text == "375.00"


async def test_una_sola_fecha_no_fuerza_multigrupo(db_session):
    fecha = _fecha_futura(5)
    v1 = await _vencimiento(db_session, 10, fecha, "50.0000")
    v2 = await _vencimiento(db_session, 10, fecha, "50.0000")
    remesa = await crear_remesa(
        db_session,
        10,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[v1.id, v2.id],
    )
    remesa, _blob, contenido = await emitir_remesa(
        db_session, 10, remesa.id, emisor=EMISOR
    )
    root = ElementTree.fromstring(contenido)
    assert len(root.find(_tag("CstmrDrctDbtInitn")).findall(_tag("PmtInf"))) == 1