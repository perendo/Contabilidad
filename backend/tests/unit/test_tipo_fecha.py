"""Tipo de cambio de la fecha (SPEC-016 T014).

Sin tipo para la fecha y sin tipo explícito -> 422; tipo explícito persistido
y sellado en la misma transacción (asiento en divisa lo crea y lo sella).
"""

from __future__ import annotations


def test_sin_tipo_para_la_fecha_ni_explicito_422(forex_client):
    fx = forex_client
    # El fixture registra USD pero ningún tipo para 2026-10-02
    resp = fx.asiento_divisa(empresa_id=10, fecha="2026-10-02")
    assert resp.status_code == 422


def test_tipo_explicito_persistido_como_tipo_de_la_fecha(forex_client):
    fx = forex_client
    resp = fx.asiento_divisa(
        empresa_id=10,
        fecha="2026-10-02",
        ratio_explicito={"ratio": "1.09000000"},
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["ratio"] == "1.09000000"
    # El tipo queda sellado en la misma transacción
    assert cuerpo["sellado"] is True
    assert cuerpo["usos_posteados"] == 1

    # El tipo explícito quedó persistido para esa fecha
    tipos = fx.get(10, "/api/v1/tipos-cambio", divisa_id=fx.divisas(10)["usd"])
    assert tipos.status_code == 200
    items = tipos.json()["items"]
    assert any(t["fecha"] == "2026-10-02" and t["ratio"] == "1.09000000" for t in items)


def test_asiento_con_tipo_existente_usa_el_de_la_fecha(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    assert resp.status_code == 201
    assert resp.json()["ratio"] == "1.08500000"


def test_tipo_anterior_usado_como_fallback(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    # Sin tipo explícito en una fecha posterior: se usa el último tipo anterior
    resp = fx.asiento_divisa(empresa_id=10, fecha="2026-10-15")
    assert resp.status_code == 201
    assert resp.json()["ratio"] == "1.08500000"