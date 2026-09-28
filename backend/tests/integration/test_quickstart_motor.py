"""Integration tests SPEC-002 T039: escenarios del quickstart de SPEC-002."""

from __future__ import annotations

from sqlalchemy import func, select

from models.acct.journal import JournalEntry


async def test_escenario_1_crear_y_asentar(journal_api):
    """S1: asiento balanceado 201 → POSTED numero=1 ejercicio=2026."""
    respuesta = journal_api.crear(fecha="2026-10-01", concepto="Venta a crédito")
    assert respuesta.status_code == 201
    body = respuesta.json()
    assert body["estado"] == "DRAFT"
    assert body["suma_debe"] == body["suma_haber"] == "100.0000"

    asentado = journal_api.asentar(body["id"])
    assert asentado.status_code == 200
    assert asentado.json()["numero"] == 1
    assert asentado.json()["ejercicio"] == 2026


async def test_escenario_2_rechazo_sin_rastro(journal_api):
    """S2: asiento desbalanceado → 422 y sin filas huérfanas."""
    c = journal_api.cuentas["a"]
    respuesta = journal_api.crear(
        fecha="2026-10-01",
        concepto="Mal",
        lineas=[
            {"account_id": c["4300"], "debit": "100.0000", "credit": "0"},
            {"account_id": c["5720"], "debit": "0", "credit": "99.0000"},
        ],
    )
    assert respuesta.status_code == 422

    async def _count(s):
        return await s.scalar(select(func.count()).select_from(JournalEntry))

    assert await journal_api.consultar(_count) == 0


async def test_escenario_4_anulacion_y_doble_anulacion(journal_api):
    """S4: REVERSAL 201, doble anulación 409, original intacto."""
    creado = journal_api.crear(fecha="2026-10-01", concepto="Anular")
    entry_id = creado.json()["id"]
    assert journal_api.asentar(entry_id).status_code == 200

    anulacion = journal_api.anular(entry_id, fecha="2026-10-05")
    assert anulacion.status_code == 201
    assert anulacion.json()["numero_reversal"] == 2
    assert anulacion.json()["estado_original"] == "CANCELLED"

    segunda = journal_api.anular(entry_id)
    assert segunda.status_code == 409

    detalle = journal_api.detalle(entry_id)
    assert detalle.json()["estado"] == "CANCELLED"
    assert detalle.json()["numero"] == 1


async def test_escenario_3_y_6_diario_y_aislamiento(journal_api):
    """S3: diario paginado por (fecha, numero); S6: B no ve nada de A."""
    creado_a = journal_api.crear(empresa_id=10, fecha="2026-10-01", concepto="A")
    assert journal_api.asentar(creado_a.json()["id"]).status_code == 200

    diario_a = journal_api.diario(
        empresa_id=10, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert diario_a.status_code == 200
    assert diario_a.json()["total"] == 1
    assert diario_a.json()["items"][0]["concepto"] == "A"

    desde_b = journal_api.diario(
        empresa_id=20, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert desde_b.json()["total"] == 0
    assert journal_api.detalle(creado_a.json()["id"], empresa_id=20).status_code == 404


async def test_escenario_5_correlatividad_10(journal_api):
    """S5: 10 asientos del mismo ejercicio numerados 1..10 sin agujeros."""
    ids = []
    for _ in range(10):
        creado = journal_api.crear(fecha="2026-10-01", concepto=f"C{_+1}")
        assert creado.status_code == 201
        ids.append(creado.json()["id"])
    for entry_id in ids:
        assert journal_api.asentar(entry_id).status_code == 200

    async def _numeros(s):
        return sorted(
            await s.scalars(
                select(JournalEntry.numero_asiento).where(
                    JournalEntry.empresa_id == 10, JournalEntry.ejercicio == 2026
                )
            )
        )

    assert await journal_api.consultar(_numeros) == list(range(1, 11))


async def test_escenario_6_ejercicio_fuera_de_rango(journal_api):
    """Fecha fuera de 2000..2100 → código ejercicio_invalido."""
    respuesta = journal_api.crear(fecha="1990-01-01", concepto="Invalido")
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"]["code"] == "ejercicio_invalido"