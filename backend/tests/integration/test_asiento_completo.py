"""Integration tests SPEC-002 T021: flujo completo crear + asentar (US1)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.audit.audit_log import AuditLog


async def test_crear_y_asentar_numero_correlativo(journal_api):
    respuesta = journal_api.crear(fecha="2026-10-01", concepto="Venta a crédito")
    assert respuesta.status_code == 201
    body = respuesta.json()
    assert body["estado"] == "DRAFT"
    assert body["suma_debe"] == body["suma_haber"] == "100.0000"
    entry_id = body["id"]

    asentado = journal_api.asentar(entry_id)
    assert asentado.status_code == 200
    detalle = asentado.json()
    assert detalle["estado"] == "POSTED"
    assert detalle["numero"] == 1
    assert detalle["ejercicio"] == 2026


async def test_numero_correlativo_en_db(journal_api):
    for i in range(3):
        creado = journal_api.crear(
            fecha="2026-10-01", concepto=f"Asiento {i+1}"
        )
        assert creado.status_code == 201
        asentado = journal_api.asentar(creado.json()["id"])
        assert asentado.status_code == 200
        assert asentado.json()["numero"] == i + 1

    async def _numeros(s):
        return list(
            await s.scalars(
                select(JournalEntry.numero_asiento)
                .where(
                    JournalEntry.empresa_id == 10,
                    JournalEntry.ejercicio == 2026,
                )
                .order_by(JournalEntry.numero_asiento)
            )
        )

    numeros = await journal_api.consultar(_numeros)
    assert numeros == [1, 2, 3]


async def test_balance_en_db_tras_asentar(journal_api):
    import uuid

    creado = journal_api.crear(fecha="2026-10-01", concepto="Venta")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200
    entry_uuid = uuid.UUID(entry_id)

    async def _checks(s):
        debe = await s.scalar(
            select(func.sum(JournalEntryLine.debe)).where(
                JournalEntryLine.journal_entry_id == entry_uuid
            )
        )
        haber = await s.scalar(
            select(func.sum(JournalEntryLine.haber)).where(
                JournalEntryLine.journal_entry_id == entry_uuid
            )
        )
        estado = await s.scalar(select(JournalEntry.estado).where(JournalEntry.id == entry_uuid))
        return Decimal(str(debe)), Decimal(str(haber)), estado

    debe, haber, estado = await journal_api.consultar(_checks)
    assert estado == JournalEntryEstado.POSTED
    assert debe == haber == Decimal("100.0000")


async def test_auditoria_create_posted_misma_transaccion(journal_api):
    import uuid

    creado = journal_api.crear(fecha="2026-10-01", concepto="Ventas")
    entry_id = creado.json()["id"]
    entry_uuid = uuid.UUID(entry_id)
    assert journal_api.asentar(entry_id).status_code == 200

    async def _audits(s):
        return list(
            await s.scalars(
                select(AuditLog.operacion).where(
                    AuditLog.empresa_id == 10,
                    AuditLog.entidad_id == str(entry_uuid),
                )
            )
        )

    assert sorted(await journal_api.consultar(_audits)) == ["CREATE", "POSTED"]


async def test_borrador_no_numero_hasta_asentar(journal_api):
    creado = journal_api.crear(fecha="2026-10-01", concepto="Borrador")
    entry_id = creado.json()["id"]
    detalle = journal_api.detalle(entry_id)
    assert detalle.status_code == 200
    assert detalle.json()["estado"] == "DRAFT"
    assert detalle.json()["numero"] is None


async def test_asentar_no_persistido_en_cascada_cross(journal_api):
    """Aislamiento: asentar desde la empresa B un borrador de A → 404."""
    creado = journal_api.crear(fecha="2026-10-01", concepto="Ventas")
    entry_id = creado.json()["id"]
    respuesta = journal_api.asentar(entry_id, empresa_id=20)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "asiento_no_encontrado"