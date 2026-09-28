"""Integration tests SPEC-002 T036: aislamiento de anulación (US3)."""

from __future__ import annotations


async def test_anular_asiento_de_a_desde_b_404_sin_efectos(journal_api):
    creado_a = journal_api.crear(empresa_id=10, fecha="2026-10-01", concepto="Solo A")
    entry_a = creado_a.json()["id"]
    assert journal_api.asentar(entry_a, empresa_id=10).status_code == 200

    respuesta = journal_api.anular(entry_a, empresa_id=20)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "asiento_no_encontrado"

    detalle = journal_api.detalle(entry_a, empresa_id=10)
    assert detalle.json()["estado"] == "POSTED"


async def test_anular_reversal_de_b_no_aparece_en_a(journal_api):
    """El rectificativo de la empresa B no es anulable ni visible desde A."""
    creado_b = journal_api.crear(empresa_id=20, fecha="2026-10-01", concepto="B solo")
    entry_b = creado_b.json()["id"]
    assert journal_api.asentar(entry_b, empresa_id=20).status_code == 200
    assert journal_api.anular(entry_b, empresa_id=20).status_code == 201

    diario_a = journal_api.diario(
        empresa_id=10, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert diario_a.json()["total"] == 0