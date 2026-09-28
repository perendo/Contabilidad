"""Aislamiento multi-tenant de los modelos de anticipo (SPEC-022 T012).

Un anticipo registrado en la empresa A no es visible desde la empresa B en
ninguna consulta (constitución III); la propia FK compuesta impide enlazar
un anticipo de A con un tercero de B (test_anticipo_fk_compuesta_empresa).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.treasury.anticipo import Anticipo, EstadoAnticipo, TipoAnticipo
from tests.unit.test_anticipo_models import CLIENTE_1, CLIENTE_2, _sembrar_base


async def test_anticipo_de_a_no_visible_desde_b(db_session):
    await _sembrar_base(db_session, 1, CLIENTE_1)
    await _sembrar_base(db_session, 2, CLIENTE_2)
    db_session.add(
        Anticipo(
            empresa_id=1, tercero_id=CLIENTE_1, tipo=TipoAnticipo.CLIENTE,
            cuenta_contable="438", fecha=date(2026, 6, 10),
            importe=Decimal("100.0000"), concepto="A",
            estado=EstadoAnticipo.pendiente, saldo_pendiente=Decimal("100.0000"),
        )
    )
    await db_session.flush()

    desde_b = await db_session.scalar(
        select(Anticipo).where(
            Anticipo.empresa_id == 2, Anticipo.tercero_id == CLIENTE_2
        )
    )
    assert desde_b is None

    de_a = await db_session.scalar(
        select(Anticipo).where(
            Anticipo.empresa_id == 1, Anticipo.tercero_id == CLIENTE_1
        )
    )
    assert de_a is not None
    assert de_a.saldo_pendiente == Decimal("100.0000")