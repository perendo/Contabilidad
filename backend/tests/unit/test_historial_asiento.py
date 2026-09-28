"""Historial por asiento (SPEC-016 T035).

El tipo consultado por asiento id coincide con el usado y es sellado=true
(FR-003 / SC-002).
"""

from __future__ import annotations


def test_historial_por_asiento_coincide_con_usado(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    assert resp.status_code == 201
    asiento_id = resp.json()["asiento_id"]

    historial = fx.get(10, "/api/v1/tipos-cambio/historial", asiento_id=asiento_id)
    assert historial.status_code == 200
    items = historial.json()["items"]
    assert len(items) == 1
    assert items[0]["asiento_id"] == asiento_id
    assert items[0]["ratio"] == "1.08500000"
    assert items[0]["sellado"] is True


def test_historial_por_asiento_inexistente_404(forex_client):
    fx = forex_client
    historial = fx.get(
        10, "/api/v1/tipos-cambio/historial",
        asiento_id="00000000-0000-0000-0000-000000000001",
    )
    assert historial.status_code == 404