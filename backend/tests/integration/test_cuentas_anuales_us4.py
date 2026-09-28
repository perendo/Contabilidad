"""Tests de integracion US4 de cuentas anuales (SPEC-010): EFE."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine


def _efe(fac, empresa_id=10, **params):
    return fac.get(empresa_id, "/api/v1/cuentas-anuales/2026/efe", **params)


def test_efe_cuadra(cuentas_client) -> None:
    fac = cuentas_client
    r = _efe(fac)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cuadre"] is True
    assert data["saldo_inicial_tesoreria"] == "0.0000"
    assert data["variacion_neta"] == "5000.0000"
    assert data["saldo_final_tesoreria"] == "5000.0000"
    assert data["variacion_balance"] == data["variacion_neta"]


def test_efe_clasificacion_por_actividad(cuentas_client) -> None:
    fac = cuentas_client
    acts = _efe(fac).json()["actividades"]
    assert acts["financiacion"]["neto"] == "10000.0000"
    assert acts["inversion"]["neto"] == "-3000.0000"
    assert acts["operativa"]["neto"] == "-2000.0000"


async def _linea_inversion(session) -> uuid.UUID:
    fila = await session.scalar(
        select(JournalEntryLine.id)
        .join(
            JournalEntry,
            (JournalEntryLine.journal_entry_id == JournalEntry.id)
            & (JournalEntryLine.empresa_id == JournalEntry.empresa_id),
        )
        .where(
            JournalEntryLine.empresa_id == 10,
            JournalEntry.ejercicio == 2026,
            JournalEntryLine.cuenta == "5720",
            JournalEntryLine.haber == Decimal("3000.0000"),
        )
    )
    assert fila is not None
    return fila


def test_efe_reasignacion_manual(cuentas_client) -> None:
    fac = cuentas_client
    linea = fac.run(fac.consultar(_linea_inversion))
    r = fac.patch(
        "/api/v1/cuentas-anuales/2026/efe/clasificacion",
        json={"movimiento_id": str(linea), "actividad": "operativa", "motivo": "ajuste"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["actividad"] == "operativa"

    acts = _efe(fac).json()["actividades"]
    assert acts["inversion"]["neto"] == "0.0000"
    assert acts["operativa"]["neto"] == "-5000.0000"


def test_efe_movimiento_inexistente_404(cuentas_client) -> None:
    fac = cuentas_client
    r = fac.patch(
        "/api/v1/cuentas-anuales/2026/efe/clasificacion",
        json={"movimiento_id": str(uuid.uuid4()), "actividad": "inversion"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "movimiento_no_encontrado"


def test_efe_multi_tenant(cuentas_client) -> None:
    fac = cuentas_client
    a = _efe(fac, empresa_id=10).json()
    b = _efe(fac, empresa_id=20).json()
    assert a["variacion_neta"] == "5000.0000"
    assert b["variacion_neta"] == "2000.0000"