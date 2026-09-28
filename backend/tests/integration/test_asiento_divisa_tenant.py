"""Aislamiento multi-tenant US1 (SPEC-016 T015 + T023).

El asiento en divisa de A no es visible para B (404), B no puede usar el tipo
de A, y la numeración es por empresa+ejercicio sin mezclar.
"""

from __future__ import annotations


def test_asiento_de_A_invisible_para_B(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=10)
    assert resp.status_code == 201
    asiento_id = resp.json()["asiento_id"]

    detalle_b = fx.get(20, f"/api/v1/asientos-divisa/{asiento_id}")
    assert detalle_b.status_code == 404
    # A sí lo ve
    detalle_a = fx.get(10, f"/api/v1/asientos-divisa/{asiento_id}")
    assert detalle_a.status_code == 200


def test_B_no_puede_usar_el_tipo_de_A(forex_client):
    fx = forex_client
    tipo_a = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    assert tipo_a.status_code == 201
    tipo_id = tipo_a.json()["id"]

    cuentas_b = fx.cuentas(20)
    resp = fx.asiento_divisa(
        empresa_id=20,
        fecha="2026-10-01",
        divisa_id=fx.divisas(20)["usd"],
        tipo_cambio_id=tipo_id,  # tipo de A usado por B
        lineas=[
            {"cuenta_id": cuentas_b["4300"], "debe_divisa": "1000.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas_b["5720"], "debe_divisa": "0.0000", "haber_divisa": "1000.0000"},
        ],
    )
    assert resp.status_code != 201  # 422 tipo_invalido / no pertenece a B


def test_numeracion_por_empresa_sin_mezcla(forex_client):
    fx = forex_client
    # A registra y asienta el primero
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp_a = fx.asiento_divisa(empresa_id=10)
    assert resp_a.status_code == 201
    assert resp_a.json()["numero_asiento"] == 1

    # B también empieza en 1 (su propia correlatividad)
    fx.registrar_tipo(empresa_id=20, fecha="2026-10-01", ratio="1.07300000")
    resp_b = fx.asiento_divisa(empresa_id=20)
    assert resp_b.status_code == 201
    assert resp_b.json()["numero_asiento"] == 1

    # Segundo asiento de A -> numero 2
    resp_a2 = fx.asiento_divisa(empresa_id=10)
    assert resp_a2.status_code == 201
    assert resp_a2.json()["numero_asiento"] == 2


def test_B_no_ve_los_tipos_de_A(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    tipos_a = fx.get(10, "/api/v1/tipos-cambio", divisa_id=fx.divisas(10)["usd"])
    tipos_b = fx.get(20, "/api/v1/tipos-cambio", divisa_id=fx.divisas(20)["usd"])
    assert tipos_a.json()["total"] == 1
    assert tipos_b.json()["total"] == 0