from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.audit.audit_log import AuditLog
from models.fiscal.liquidacion_retenciones import (
    EstadoLiquidacionRetenciones,
    LiquidacionRetenciones,
)
from services.fiscal.liquidacion_retenciones import contabilizar_liquidacion
from tests.conftest import sembrar_empresa_pgc


async def _crear_liquidacion(db, total: Decimal = Decimal("5000.0000")) -> uuid.UUID:
    await sembrar_empresa_pgc(db, 1)
    liquidacion = LiquidacionRetenciones(
        empresa_id=1,
        ejercicio=2025,
        trimestre=3,
        periodo="2025-Q3",
        total_base_retenciones=Decimal("33333.3333"),
        total_retenciones=total,
        n_perceptores=1,
    )
    db.add(liquidacion)
    await db.flush()
    return liquidacion.id


async def test_asiento_liquidacion_retenciones_4751_contra_banco(db_session):
    liquidacion_id = await _crear_liquidacion(db_session)
    fecha = date(2025, 9, 30)

    resultado = await contabilizar_liquidacion(
        db_session,
        liquidacion_id=liquidacion_id,
        empresa_id=1,
        fecha_asiento=fecha,
        actor="admin@test",
        ip="127.0.0.1",
    )
    await db_session.flush()

    assert resultado["estado"] == EstadoLiquidacionRetenciones.liquidado
    assert resultado["fecha_liquidacion"] == fecha
    assert resultado["total_retenciones"] == Decimal("5000.0000")

    asiento_id = resultado["asiento_id"]
    assert isinstance(asiento_id, uuid.UUID)
    asiento = await db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == 1,
            JournalEntry.id == asiento_id,
        )
    )
    assert asiento is not None
    assert asiento.estado == JournalEntryEstado.POSTED
    assert asiento.fecha == fecha
    assert "2025-Q3" in asiento.concepto

    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.empresa_id == 1,
                JournalEntryLine.journal_entry_id == asiento_id,
            )
        )
    ).all()
    assert len(lineas) == 2
    assert sum((linea.debe for linea in lineas), Decimal("0.0000")) == Decimal("5000.0000")
    assert sum((linea.haber for linea in lineas), Decimal("0.0000")) == Decimal("5000.0000")
    cuentas = {linea.cuenta: linea for linea in lineas}
    assert cuentas["4751"].debe == Decimal("5000.0000")
    assert cuentas["4751"].haber == Decimal("0.0000")
    assert cuentas["5720"].debe == Decimal("0.0000")
    assert cuentas["5720"].haber == Decimal("5000.0000")

    liquidacion = await db_session.get(LiquidacionRetenciones, liquidacion_id)
    assert liquidacion is not None
    assert liquidacion.estado == EstadoLiquidacionRetenciones.liquidado
    assert liquidacion.asiento_id == asiento_id
    assert liquidacion.fecha_liquidacion == fecha

    auditoria = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.empresa_id == 1,
            AuditLog.operacion == "CONTABILIZAR_LIQUIDACION",
        )
    )
    assert auditoria is not None
    assert auditoria.usuario == "admin@test"
    assert auditoria.ip == "127.0.0.1"
