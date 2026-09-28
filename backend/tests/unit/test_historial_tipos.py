"""Histórico de tipos por divisa/fecha (SPEC-016 T033).

Consultas por divisa, por rango de fechas y por sellado; los tipos sellados
siguen visibles en el histórico.
"""

from __future__ import annotations


def test_historial_por_divisa_y_fecha(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-15", ratio="1.09000000")

    por_divisa = fx.get(10, "/api/v1/tipos-cambio", divisa_id=fx.divisas(10)["usd"])
    assert por_divisa.json()["total"] == 2

    en_rango = fx.get(10, "/api/v1/tipos-cambio",
                      divisa_id=fx.divisas(10)["usd"],
                      fecha_gte="2026-10-01", fecha_lte="2026-10-10")
    assert en_rango.json()["total"] == 1
    assert en_rango.json()["items"][0]["fecha"] == "2026-10-01"


def test_sellados_siguen_visibles(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")  # sella el tipo

    sellados = fx.get(10, "/api/v1/tipos-cambio", sellado=True)
    no_sellados = fx.get(10, "/api/v1/tipos-cambio", sellado=False)
    todos = fx.get(10, "/api/v1/tipos-cambio")
    assert sellados.json()["total"] == 1
    assert no_sellados.json()["total"] == 0
    assert todos.json()["total"] == 1
    assert todos.json()["items"][0]["sellado"] is True
    assert todos.json()["items"][0]["usos_posteados"] == 1


def test_historial_por_divisa_y_rango(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.registrar_tipo(empresa_id=10, fecha="2026-11-05", ratio="1.10000000")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.12000000")

    rango = fx.get(10, "/api/v1/tipos-cambio/historial",
                   divisa_id=fx.divisas(10)["usd"],
                   fecha_desde="2026-11-01", fecha_hasta="2026-12-31")
    assert rango.json()["total"] == 2
    fechas = {i["fecha"] for i in rango.json()["items"]}
    assert fechas == {"2026-11-05", "2026-12-31"}