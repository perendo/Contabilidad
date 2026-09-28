"""Correlativity tests (T014).

FR-004 / constitución IV: remesa numbering is sequential without gaps per
(empresa, ejercicio) and independent between ejercicios.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from services.remittance.emision import crear_remesa
from services.remittance.seleccion import siguiente_numero_remesa


async def _vencimiento(
    session: AsyncSession, empresa_id: int, importe: str = "150.0000"
) -> Vencimiento:
    vencimiento = Vencimiento(
        empresa_id=empresa_id,
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
    return vencimiento


async def test_tres_remesas_consecutivas_sin_saltos(db_session):
    v1 = await _vencimiento(db_session, 1, "100.0000")
    v2 = await _vencimiento(db_session, 1, "200.0000")
    v3 = await _vencimiento(db_session, 1, "50.0000")

    r1 = await crear_remesa(
        db_session, 1, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v1.id]
    )
    r2 = await crear_remesa(
        db_session, 1, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v2.id]
    )
    r3 = await crear_remesa(
        db_session, 1, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v3.id]
    )
    await db_session.commit()

    assert (r1.numero_remesa, r2.numero_remesa, r3.numero_remesa) == (1, 2, 3)
    assert r3.importe_total == Decimal("50.0000")
    assert r1.ejercicio == r2.ejercicio == r3.ejercicio == 2026


async def test_secuencia_avanza_tras_las_creadas(db_session):
    v = await _vencimiento(db_session, 1)
    await crear_remesa(
        db_session, 1, formato="CSB_19_19", tipo_adeudo="CORE", vencimiento_ids=[v.id]
    )
    assert await siguiente_numero_remesa(db_session, 1, 2026) == 2


async def test_secuencia_independiente_por_ejercicio(db_session):
    v = await _vencimiento(db_session, 1)
    await crear_remesa(
        db_session, 1, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v.id]
    )

    assert await siguiente_numero_remesa(db_session, 1, 2025) == 1
    assert await siguiente_numero_remesa(db_session, 1, 2027) == 1


async def test_numeracion_independiente_por_empresa(db_session):
    v_a = await _vencimiento(db_session, 1)
    v_b = await _vencimiento(db_session, 2)
    await crear_remesa(
        db_session, 1, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v_a.id]
    )
    await crear_remesa(
        db_session, 2, formato="SEPA_DD", tipo_adeudo="CORE", vencimiento_ids=[v_b.id]
    )
    assert await siguiente_numero_remesa(db_session, 2, 2026) == 2
    assert await siguiente_numero_remesa(db_session, 1, 2026) == 2