"""Reclasificacion balanceada (SPEC-025 T033/T046, constitucion I).

Preview solo lectura, confirmacion con asiento ADJUSTMENT balanceado
(Debe == Haber == importe), transiciones borrador -> contabilizado ->
cuadrado, auditoria RECLASIFICAR, ejercicio fuera de rango 422 y ejercicio
cerrado 409.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.audit.audit_log import AuditLog
from models.catalog.reclasificacion_saldo import (
    EstadoReclasificacion,
    ReclasificacionSaldo,
)
from services.catalog.errores import CatalogoError
from services.catalog.reclasificacion_saldos import (
    confirmar_reclasificacion,
    preview_reclasificacion,
)
from tests.unit.catalogo_support import preparar_trasvase


async def test_preview_no_escribe(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    asientos_antes = int(
        await db_session.scalar(select(func.count()).select_from(JournalEntry)) or 0
    )

    preview = await preview_reclasificacion(
        db_session, empresa_id=10, version_id=objetivo, ejercicio=2025
    )

    assert len(preview["items"]) == 1
    item = preview["items"][0]
    assert item["codigo_origen"] == "4300"
    assert item["codigo_destino"] == "4310"
    assert item["importe"] == "12500.0000"
    assert isinstance(item["cuenta_origen_id"], int)
    assert item["cuenta_destino_id"]
    assert item["mapeo_id"]
    assert preview["total_importe"] == "12500.0000"

    asientos_despues = int(
        await db_session.scalar(select(func.count()).select_from(JournalEntry)) or 0
    )
    assert asientos_despues == asientos_antes
    filas = int(
        await db_session.scalar(
            select(func.count()).select_from(ReclasificacionSaldo)
        )
        or 0
    )
    assert filas == 0


async def test_confirm_asiento_balanceado_y_estado(db_session):
    _base, objetivo, ids = await preparar_trasvase(db_session)
    preview = await preview_reclasificacion(
        db_session, empresa_id=10, version_id=objetivo, ejercicio=2025
    )
    assert preview["total_importe"] == "12500.0000"

    resultado = await confirmar_reclasificacion(
        db_session,
        empresa_id=10,
        version_id=objetivo,
        ejercicio=2025,
        items=None,
        actor="test",
    )

    assert resultado["reclasificaciones"] == 1
    assert resultado["total_importe"] == "12500.0000"
    assert len(resultado["asientos"]) == 1
    assert resultado["asientos"][0]["cuadre"] is True

    entry_id = uuid.UUID(resultado["asientos"][0]["asiento_id"])
    entrada = await db_session.get(JournalEntry, entry_id)
    assert entrada is not None
    assert entrada.estado == JournalEntryEstado.POSTED
    assert entrada.tipo == JournalEntryTipo.ADJUSTMENT
    assert entrada.ejercicio == 2025

    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == entry_id
            )
        )
    ).all()
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    assert debe == haber == Decimal("12500.0000")
    por_cuenta = {l.cuenta: (l.debe, l.haber) for l in lineas}
    assert por_cuenta["4310"] == (Decimal("12500.0000"), Decimal(0))
    assert por_cuenta["4300"] == (Decimal(0), Decimal("12500.0000"))

    fila = await db_session.scalar(
        select(ReclasificacionSaldo).where(
            ReclasificacionSaldo.empresa_id == 10,
            ReclasificacionSaldo.version_destino_id == uuid.UUID(objetivo),
        )
    )
    assert fila is not None
    assert fila.estado == EstadoReclasificacion.cuadrado
    assert fila.importe == Decimal("12500.0000")
    assert fila.cuenta_origen_id == ids["4300"]
    assert fila.asiento_id == entry_id
    assert fila.version_destino_id == uuid.UUID(objetivo)

    auditoria = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.operacion == "RECLASIFICAR")
        )
    ).all()
    assert len(auditoria) == 1
    assert auditoria[0].empresa_id == 10


async def test_confirm_signo_negativo(db_session):
    from tests.unit.catalogo_support import plan_ids, postear, sembrar_base

    await sembrar_base(db_session)
    objetivo = await _objetivo(db_session)
    ids = await plan_ids(db_session)
    await postear(
        db_session,
        10,
        date(2025, 6, 30),
        [
            {"account_id": ids["1110"], "debit": "800.0000", "credit": "0"},
            {"account_id": ids["4300"], "debit": "0", "credit": "800.0000"},
        ],
        concepto="Cobro indebido",
    )

    preview = await preview_reclasificacion(
        db_session, empresa_id=10, version_id=objetivo, ejercicio=2025
    )
    assert preview["items"][0]["importe"] == "800.0000"

    resultado = await confirmar_reclasificacion(
        db_session,
        empresa_id=10,
        version_id=objetivo,
        ejercicio=2025,
        items=None,
        actor="test",
    )
    assert resultado["reclasificaciones"] == 1
    entry_id = uuid.UUID(resultado["asientos"][0]["asiento_id"])
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == entry_id
            )
        )
    ).all()
    por_cuenta = {l.cuenta: (l.debe, l.haber) for l in lineas}
    assert por_cuenta["4300"] == (Decimal("800.0000"), Decimal(0))
    assert por_cuenta["4310"] == (Decimal(0), Decimal("800.0000"))
    assert sum((l.debe for l in lineas), Decimal(0)) == sum(
        (l.haber for l in lineas), Decimal(0)
    )


async def test_ejercicio_fuera_de_rango_422(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    with pytest.raises(CatalogoError) as exc:
        await preview_reclasificacion(
            db_session, empresa_id=10, version_id=objetivo, ejercicio=1999
        )
    assert exc.value.code == "ejercicio_invalido"
    assert exc.value.status_code == 422


async def test_ejercicio_cerrado_409(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    db_session.add(
        FiscalYear(
            empresa_id=10,
            year=2025,
            date_start=date(2025, 1, 1),
            date_end=date(2025, 12, 31),
            is_closed=True,
            cierre_entry_id=None,
        )
    )
    await db_session.flush()

    with pytest.raises(CatalogoError) as exc:
        await confirmar_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=objetivo,
            ejercicio=2025,
            items=None,
            actor="test",
        )
    assert exc.value.code == "ejercicio_cerrado"
    assert exc.value.status_code == 409


async def _objetivo(db_session) -> str:
    from tests.unit.catalogo_support import objetivo_2026

    return str((await objetivo_2026(db_session)).id)
