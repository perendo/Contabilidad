"""Aislamiento multi-tenant US3 (SPEC-016 T036 + T042).

La empresa B no ve el historial de tipos de A y no puede corregir un tipo de A
(404); A sella y bloquea sus tipos, B opera con sus propios recursos.
"""

from __future__ import annotations


def test_B_no_ve_historial_de_A(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp_a = fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    asiento_id = resp_a.json()["asiento_id"]

    historial_b = fx.get(20, "/api/v1/tipos-cambio/historial", asiento_id=asiento_id)
    assert historial_b.status_code == 404

    # B tampoco ve los tipos de A en su histórico
    historial_b_rango = fx.get(
        20, "/api/v1/tipos-cambio/historial",
        divisa_id=fx.divisas(20)["usd"],
    )
    assert historial_b_rango.json()["total"] == 0

    # A sí ve el historial de su asiento
    historial_a = fx.get(10, "/api/v1/tipos-cambio/historial", asiento_id=asiento_id)
    assert historial_a.status_code == 200
    assert historial_a.json()["items"][0]["sellado"] is True


def test_B_no_puede_corregir_tipo_de_A(forex_client):
    fx = forex_client
    tipo_a = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    assert tipo_a.status_code == 201
    tipo_id = tipo_a.json()["id"]

    resp = fx.patch(f"/api/v1/tipos-cambio/{tipo_id}", empresa_id=20,
                    json={"ratio": "1.20000000", "motivo": "intento B"})
    assert resp.status_code == 404


def test_escenario_completo_A_sella_B_no_mezcla(forex_client):
    fx = forex_client
    # A registra y sella su tipo
    tipo_a = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    tipo_a_id = tipo_a.json()["id"]
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")

    # B no puede corregir el tipo sellado de A (ni por inexistencia ni por sello)
    resp_b_patch = fx.patch(f"/api/v1/tipos-cambio/{tipo_a_id}", empresa_id=20,
                            json={"ratio": "1.20000000", "motivo": "intento"})
    assert resp_b_patch.status_code == 404

    # B registra y usa su propio tipo, sin verse afectado por A
    tipo_b = fx.registrar_tipo(empresa_id=20, fecha="2026-11-01", ratio="1.05000000")
    assert tipo_b.status_code == 201
    assert tipo_b.json()["sellado"] is False
    asiento_b = fx.asiento_divisa(empresa_id=20, fecha="2026-11-01")
    assert asiento_b.status_code == 201

    # El historial de B muestra solo lo de B
    hist_b = fx.get(20, "/api/v1/tipos-cambio", sellado=True)
    assert hist_b.json()["total"] == 1
    hist_a = fx.get(10, "/api/v1/tipos-cambio", sellado=True)
    assert hist_a.json()["total"] == 1