"""Tests SPEC-011 US3 (T029/T036): antigüedad de saldos por rangos."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from services.treasury.antiguedad import calcular_antiguedad
from tests.conftest import crear_empresa


async def _escenario(db: AsyncSession) -> uuid.UUID:
    await crear_empresa(db, 10, nif="T00000010", razon_social="E10 SL")
    await db.flush()
    t = Tercero(empresa_id=10, nombre="Cliente", nif=None, es_cliente=True)
    db.add(t)
    await db.flush()
    corte = date(2026, 6, 30)
    for dias, importe in ((10, "10.0000"), (45, "20.0000"), (75, "30.0000"), (95, "40.0000")):
        db.add(
            Vencimiento(
                empresa_id=10, tercero_id=t.id, factura_id=None,
                recibo_num=f"R-{dias}", iban="ES9121000418450200051332", ejercicio=2026,
                fecha_vencimiento=corte - timedelta(days=dias),
                importe=Decimal(importe), estado=EstadoVencimiento.pendiente,
            )
        )
    await db.flush()
    return t.id


async def test_clasificacion_por_rangos_y_suma(db_session: AsyncSession) -> None:
    await _escenario(db_session)
    informe = await calcular_antiguedad(db_session, empresa_id=10, fecha_corte=date(2026, 6, 30))
    assert informe["total"] == "100.0000"
    fila = informe["items"][0]
    assert fila["rango_30"] == "10.0000"
    assert fila["rango_60"] == "20.0000"
    assert fila["rango_90"] == "30.0000"
    assert fila["rango_90mas"] == "40.0000"


async def test_saldos_cobrados_no_computan(db_session: AsyncSession) -> None:
    t = await _escenario(db_session)
    db_session.add(
        Vencimiento(
            empresa_id=10, tercero_id=t, factura_id=None, recibo_num="R-COB",
            iban="ES9121000418450200051332", ejercicio=2026,
            fecha_vencimiento=date(2026, 6, 1), importe=Decimal("999.0000"),
            estado=EstadoVencimiento.cobrado,
        )
    )
    await db_session.flush()
    informe = await calcular_antiguedad(db_session, empresa_id=10, fecha_corte=date(2026, 6, 30))
    assert informe["total"] == "100.0000"
