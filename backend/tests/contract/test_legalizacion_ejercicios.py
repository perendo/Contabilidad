"""Contrato de ejercicios de la legalización (SPEC-019 contracts/legalizacion.md §4).

Ejercicio abierto → 409, inexistente → 404 y bloqueo FR-007: un asiento con
fecha dentro del ejercicio legalizado se rechaza tanto en el motor (servicio)
como en el trigger de base de datos, sin afectar a otros ejercicios.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo


def _abrir(ns, empresa_id=10, year=2026):
    async def _op(session):
        session.add(
            FiscalYear(
                empresa_id=empresa_id,
                year=year,
                date_start=date(year, 1, 1),
                date_end=date(year, 12, 31),
                is_closed=False,
            )
        )
        await session.flush()

    ns.run(ns.mutar(_op))


def test_ejercicio_abierto_409(ngo_client):
    ns = ngo_client
    _abrir(ns, 10, 2026)
    r = ns.post("/api/v1/legalizaciones", 10, {"ejercicio": 2026})
    assert r.status_code == 409
    assert "no está cerrado" in r.json()["detail"]


def test_ejercicio_inexistente_404(ngo_client):
    ns = ngo_client
    r = ns.post("/api/v1/legalizaciones", 10, {"ejercicio": 2030})
    assert r.status_code == 404
    assert "2030" in r.json()["detail"]


def test_fr007_bloquea_asiento_en_el_motor(ngo_client):
    ns = ngo_client
    ns.legalizar_directa(10, 2026)  # ejercicio 2026 legalizado (abierto)
    r = ns.post(
        "/api/v1/asientos",
        10,
        {
            "fecha": "2026-09-01",
            "concepto": "Bloqueado por legalización",
            "lineas": [
                {"cuenta": "6400", "debe": "100.0000", "haber": "0", "detalle": "x"},
                {"cuenta": "5720", "debe": "0", "haber": "100.0000", "detalle": "x"},
            ],
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ejercicio_legalizado"


def test_fr007_bloquea_asiento_a_nivel_de_base_de_datos(ngo_client):
    ns = ngo_client
    ns.legalizar_directa(10, 2026)

    async def _op(session):
        session.add(
            JournalEntry(
                empresa_id=10,
                ejercicio=2026,
                fecha=date(2026, 9, 2),
                tipo=JournalEntryTipo.GENERAL,
                concepto="Directo",
                numero_asiento=99,
                estado=JournalEntryEstado.POSTED,
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        ns.run(ns.mutar(_op))


def test_fr007_no_afecta_a_otros_ejercicios(ngo_client):
    ns = ngo_client
    ns.legalizar_directa(10, 2026)
    r = ns.post(
        "/api/v1/asientos",
        10,
        {
            "fecha": "2025-12-31",
            "concepto": "Ejercicio distinto al legalizado",
            "lineas": [
                {"cuenta": "6400", "debe": "50.0000", "haber": "0", "detalle": "x"},
                {"cuenta": "5720", "debe": "0", "haber": "50.0000", "detalle": "x"},
            ],
        },
    )
    assert r.status_code == 201, r.text


def test_cerrado_y_legalizado_bloquea_ejercicio_2025(ngo_client):
    """Cierre + legalización reales: el ejercicio 2025 deja de admitir asientos."""
    ns = ngo_client
    ns.cerrar(10, 2025)
    leg = ns.post("/api/v1/legalizaciones", 10, {"ejercicio": 2025})
    assert leg.status_code == 201, leg.text

    r = ns.post(
        "/api/v1/asientos",
        10,
        {
            "fecha": "2025-11-01",
            "concepto": "Posterior a la legalización",
            "lineas": [
                {"cuenta": "6400", "debe": "10.0000", "haber": "0", "detalle": "x"},
                {"cuenta": "5720", "debe": "0", "haber": "10.0000", "detalle": "x"},
            ],
        },
    )
    assert r.status_code == 400  # ejercicio_cerrado (SPEC-004) refuerza FR-007
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"