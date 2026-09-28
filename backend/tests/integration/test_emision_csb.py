"""CSB 19.19 emission integration tests (T028).

FR-003: records of exactly 120 chars, amounts in cents on records 1/3/5,
ISO-8859-15 encoding and correct totals.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from services.remittance.emision import EmisionEstadoError, crear_remesa, emitir_remesa
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _vencimiento(session, empresa_id: int, importe: str) -> Vencimiento:
    hoy = datetime.now(timezone.utc).date()
    fecha = hoy + timedelta(days=10)
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


async def test_emision_csb_registros_120_caracteres(db_session):
    v1 = await _vencimiento(db_session, 11, "150.0000")
    v2 = await _vencimiento(db_session, 11, "300.0000")
    remesa = await crear_remesa(
        db_session, 11, formato="CSB_19_19", tipo_adeudo="CORE", vencimiento_ids=[v1.id, v2.id]
    )
    remesa, blob, contenido = await emitir_remesa(
        db_session, 11, remesa.id, emisor=EMISOR
    )
    await db_session.commit()

    assert blob.tipo.value == "remesa_csb1919"
    assert blob.sha256 == hashlib.sha256(contenido).hexdigest()
    assert remesa.estado.value == "emitida"

    texto = contenido.decode("ISO-8859-15")
    lineas = texto.split("\r\n")
    tipos = [linea[0] for linea in lineas]
    assert tipos == ["1", "2", "3", "3", "5"]

    for linea in lineas:
        assert len(linea) == 120

    importe_cents = 45000
    assert int(lineas[0][66:78]) == importe_cents
    assert int(lineas[0][78:84]) == 2
    importes_recibos = {int(lineas[i][21:33]) for i in (2, 3)}
    assert importes_recibos == {15000, 30000}
    assert int(lineas[4][1:13]) == importe_cents
    assert int(lineas[4][19:23]) == importe_cents % 97


async def test_csb_adeudo_b2b_rechazado(db_session):
    v = await _vencimiento(db_session, 11, "50.0000")
    remesa = await crear_remesa(
        db_session, 11, formato="CSB_19_19", tipo_adeudo="B2B", vencimiento_ids=[v.id]
    )
    with pytest.raises(EmisionEstadoError):
        await emitir_remesa(db_session, 11, remesa.id, emisor=EMISOR)