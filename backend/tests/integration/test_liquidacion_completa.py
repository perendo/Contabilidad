from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine
from models.audit.audit_log import AuditLog
from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from services.fiscal.liquidacion_retenciones import (
    LiquidacionError,
    contabilizar_liquidacion,
)


async def _crear_liquidacion(session, empresa_id: int = 10) -> str:
    liquidacion = LiquidacionRetenciones(
        empresa_id=empresa_id,
        ejercicio=2025,
        trimestre=3,
        periodo="2025-Q3",
        total_base_retenciones=Decimal("33333.3333"),
        total_retenciones=Decimal("5000.0000"),
        n_perceptores=1,
    )
    session.add(liquidacion)
    await session.flush()
    return str(liquidacion.id)


def test_liquidacion_completa_persiste_asiento_estado_y_auditoria(retenciones_client):
    api = retenciones_client
    liquidacion_id = api.run(api.mutar(lambda session: _crear_liquidacion(session)))
    fecha = date(2025, 9, 30)

    resultado = api.run(
        api.mutar(
            lambda session: contabilizar_liquidacion(
                session,
                liquidacion_id=uuid.UUID(liquidacion_id),
                empresa_id=10,
                fecha_asiento=fecha,
                actor="admin@test",
                ip="127.0.0.1",
            )
        )
    )

    assert resultado["estado"].value == "liquidado"
    assert resultado["fecha_liquidacion"] == fecha
    assert resultado["total_retenciones"] == Decimal("5000.0000")
    asiento_id = resultado["asiento_id"]
    assert isinstance(asiento_id, uuid.UUID)

    async def _consultar(session):
        asiento = await session.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == 10,
                JournalEntry.id == asiento_id,
            )
        )
        lineas = list(
            (
                await session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.empresa_id == 10,
                        JournalEntryLine.journal_entry_id == asiento_id,
                    )
                )
            ).all()
        )
        liquidacion = await session.scalar(
            select(LiquidacionRetenciones).where(
                LiquidacionRetenciones.empresa_id == 10,
                LiquidacionRetenciones.id == uuid.UUID(liquidacion_id),
            )
        )
        auditoria = list(
            (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.empresa_id == 10,
                        AuditLog.operacion == "CONTABILIZAR_LIQUIDACION",
                    )
                )
            ).all()
        )
        return asiento, lineas, liquidacion, auditoria

    asiento, lineas, liquidacion, auditoria = api.run(api.consultar(_consultar))
    assert asiento is not None
    assert asiento.estado.value == "POSTED"
    assert asiento.fecha == fecha
    assert len(lineas) == 2
    assert sum((linea.debe for linea in lineas), Decimal("0.0000")) == Decimal("5000.0000")
    assert sum((linea.haber for linea in lineas), Decimal("0.0000")) == Decimal("5000.0000")
    assert liquidacion is not None
    assert liquidacion.estado.value == "liquidado"
    assert liquidacion.asiento_id == asiento.id
    assert liquidacion.fecha_liquidacion == fecha
    assert len(auditoria) == 1
    assert auditoria[0].entidad == "liquidacion_retenciones"
    assert json.loads(auditoria[0].payload or "{}")["asiento_id"] == str(asiento.id)

    with pytest.raises(LiquidacionError) as excinfo:
        api.run(
            api.mutar(
                lambda session: contabilizar_liquidacion(
                    session,
                    liquidacion_id=uuid.UUID(liquidacion_id),
                    empresa_id=10,
                    fecha_asiento=date(2025, 10, 1),
                )
            )
        )
    assert excinfo.value.status_code == 409

    async def _contar_asientos(session):
        return len(
            (
                await session.scalars(
                    select(JournalEntry).where(JournalEntry.empresa_id == 10)
                )
            ).all()
        )

    assert api.run(api.consultar(_contar_asientos)) == 1
