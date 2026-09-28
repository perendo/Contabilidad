"""Aislamiento multi-tenant US2 (SPEC-016 T027 + T032).

La valoración y las diferencias de cambio de A son invisibles para B; B valora
sus propios saldos sin mezclar los de A.
"""

from __future__ import annotations


def test_diferencias_de_A_invisibles_para_B(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp.status_code == 200
    assert resp.json()["n"] == 2

    # B no ve las diferencias de A
    lista_b = fx.get(20, "/api/v1/diferencias-cambio", ejercicio=2026)
    assert lista_b.json()["total"] == 0
    # A sí las ve
    lista_a = fx.get(10, "/api/v1/diferencias-cambio", ejercicio=2026)
    assert lista_a.json()["total"] == 2


def test_B_no_ve_el_asiento_de_valoracion_de_A(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    asiento_valoracion = resp.json()["asiento_id"]

    detalle_b = fx.get(20, f"/api/v1/asientos-divisa/{asiento_valoracion}")
    assert detalle_b.status_code == 404


def test_B_valora_sus_propios_saldos_sin_mezcla(forex_client):
    fx = forex_client
    # A: saldo y valoración
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    fx.post("/api/v1/valoraciones", empresa_id=10,
            json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})

    # B: su propio saldo en divisa (ratio distinto)
    fx.registrar_tipo(empresa_id=20, fecha="2026-10-01", ratio="1.05000000")
    fx.asiento_divisa(empresa_id=20, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=20, fecha="2026-12-31", ratio="1.12000000")
    resp_b = fx.post("/api/v1/valoraciones", empresa_id=20,
                     json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp_b.status_code == 200
    assert resp_b.json()["n"] == 2

    # Los 4 registros existen repartidos 2/2 (nunca mezclados)
    for empresa, esperado in ((10, 2), (20, 2)):
        lista = fx.get(empresa, "/api/v1/diferencias-cambio", ejercicio=2026)
        assert lista.json()["total"] == esperado