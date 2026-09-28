"""Legalización: restricciones de ejercicio y FR-007 (SPEC-019 US2).

La emisión exige ejercicio cerrado. Una legalización válida de un ejercicio
bloquea nuevos asientos en él tanto en el motor (servicio) como a nivel DB
(trigger SQLite; las migraciones 011_ngo.sql hacen lo propio en PostgreSQL).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from services.journal.entry_service import AsientoError
from services.ngo.errores import NgoError
from services.ngo.legalizacion import emitir_legalizacion


def _abrir(ns, empresa_id=10, year=2026):
    from models.acct.fiscal_year import FiscalYear

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


def test_emision_exige_ejercicio_cerrado(ngo_client):
    ns = ngo_client
    _abrir(ns, 10, 2026)
    with pytest.raises(NgoError) as exc:
        ns.run(ns.mutar(lambda s: emitir_legalizacion(s, empresa_id=10, ejercicio=2026)))
    assert exc.value.code == "ejercicio_abierto"

    with pytest.raises(NgoError) as exc2:
        ns.run(ns.mutar(lambda s: emitir_legalizacion(s, empresa_id=10, ejercicio=1999)))
    assert exc2.value.code == "ejercicio_inexistente"


def test_fr007_bloquea_nuevos_asientos_en_el_motor(ngo_client):
    ns = ngo_client
    ns.legalizar_directa(10, 2026)
    with pytest.raises(AsientoError) as exc:
        ns.asiento(
            10,
            [
                {"cuenta": "6400", "debe": Decimal("100.0000"), "haber": Decimal(0), "detalle": "x"},
                {"cuenta": "5720", "debe": Decimal(0), "haber": Decimal("100.0000"), "detalle": "x"},
            ],
            date(2026, 9, 1),
            "Bloqueado por legalización",
        )
    assert exc.value.code == "ejercicio_legalizado"


def test_fr007_bloquea_a_nivel_de_base_de_datos(ngo_client):
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
    entrada = ns.asiento(
        10,
        [
            {"cuenta": "6400", "debe": Decimal("50.0000"), "haber": Decimal(0), "detalle": "x"},
            {"cuenta": "5720", "debe": Decimal(0), "haber": Decimal("50.0000"), "detalle": "x"},
        ],
        date(2025, 12, 31),
        "Ejercicio distinto al legalizado",
    )
    assert entrada.id is not None and uuid.UUID(str(entrada.id)) is not None