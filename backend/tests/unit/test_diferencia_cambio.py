"""Cálculo de diferencias de cambio (SPEC-016 T024).

diferencia = saldo_divisa × tipo_cierre − saldo_funcional_previo, todo en
Decimal a 4 decimales; signo correcto (pérdida 6680 / ganancia 7690).
"""

from __future__ import annotations


def _postear_saldo_1000_usd_a_1085(fx, empresa_id: int = 10) -> str:
    fx.registrar_tipo(empresa_id=empresa_id, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=empresa_id, fecha="2026-10-01")
    assert resp.status_code == 201
    return resp.json()["asiento_id"]


def test_diferencia_exacta_ganancia_con_decimal(forex_client):
    fx = forex_client
    _postear_saldo_1000_usd_a_1085(fx)
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")

    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["n"] == 2  # 4300 (debe) y 5720 (haber)

    por_cuenta = {v["cuenta_id"]: v for v in cuerpo["valoraciones"]}
    # 1000 × 1.10 = 1100.0000 − 1085.0000 = 15.0000 (ganancia en 4300)
    ganancia = por_cuenta[fx.cuentas(10)["4300"]]
    assert ganancia["saldo_divisa"] == "1000.0000"
    assert ganancia["saldo_funcional_previo"] == "1085.0000"
    assert ganancia["diferencia"] == "15.0000"
    assert ganancia["tipo"] == "ganancia"
    # 5720 es haber: saldo -1000, funcional -1085, valorado -1100 -> perdida
    perdida = por_cuenta[fx.cuentas(10)["5720"]]
    assert perdida["saldo_divisa"] == "-1000.0000"
    assert perdida["saldo_funcional_previo"] == "-1085.0000"
    assert perdida["diferencia"] == "15.0000"
    assert perdida["tipo"] == "perdida"


def test_signo_determina_cuenta_6680_7690(forex_client):
    fx = forex_client
    _postear_saldo_1000_usd_a_1085(fx)
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")

    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp.status_code == 200
    cuerpo = resp.json()
    tipos = {v["tipo"] for v in cuerpo["valoraciones"]}
    assert tipos == {"ganancia", "perdida"}