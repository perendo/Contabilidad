"""Test cesión de cobros con comisión (SPEC-022 T031, US3).

Al ceder vencimientos pendientes se crea el asiento Debe 572 (neto) + 662
(comisión) | Haber 430 (total) con Debe == Haber; los vencimientos pasan a
``cedido`` e ``importe_neto_recibido = total - comisión``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.cesion import EstadoCesion, TipoComisionCesion
from services.treasury.cesion import contar_vencimientos, registrar_cesion
from tests.unit.anticipo_support import cuentas, sembrar_base, sumas


async def test_cesion_asiento_balanceado(db_session):
    base = await sembrar_base(db_session, 1, n_vencimientos=2)
    (v1, v2) = base["vencimientos"]

    cesion = await registrar_cesion(
        db_session,
        empresa_id=1,
        entidad_financiera="Banco X",
        fecha_cesion=date(2026, 7, 1),
        vencimiento_ids=[v1, v2],
        comision="100.0000",
        tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
    )
    await db_session.flush()

    assert cesion.estado == EstadoCesion.activa
    assert str(cesion.importe_total_cedido) == "3000.0000"
    assert str(cesion.importe_neto_recibido) == "2900.0000"
    assert str(cesion.comision) == "100.0000"
    assert await contar_vencimientos(db_session, empresa_id=1, cesion_id=cesion.id) == 2

    asiento = await db_session.get(JournalEntry, cesion.asiento_id)
    debe, haber = await sumas(db_session, asiento.id)
    assert debe == haber
    ctas = await cuentas(db_session, asiento.id)
    assert ctas["572"] == (Decimal("2900.0000"), 0)
    assert ctas["662"] == (Decimal("100.0000"), 0)
    assert ctas["430"] == (0, Decimal("3000.0000"))

    vencimientos = (
        await db_session.scalars(
            select(Vencimiento).where(
                Vencimiento.empresa_id == 1, Vencimiento.id.in_([v1, v2])
            )
        )
    ).all()
    assert len(vencimientos) == 2
    for v in vencimientos:
        assert v.estado == EstadoVencimiento.cedido


async def test_cesion_comision_porcentaje(db_session):
    base = await sembrar_base(db_session, 1, n_vencimientos=2)
    (v1, v2) = base["vencimientos"]

    cesion = await registrar_cesion(
        db_session,
        empresa_id=1,
        entidad_financiera="Banco Y",
        fecha_cesion=date(2026, 7, 2),
        vencimiento_ids=[v1, v2],
        comision="1.0000",
        tipo_comision=TipoComisionCesion.PORCENTAJE,
    )
    await db_session.flush()

    assert str(cesion.comision) == "30.0000"
    assert str(cesion.importe_neto_recibido) == "2970.0000"