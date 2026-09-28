"""Quickstart de SPEC-016 (T045).

Reproduce el escenario de arranque rápido: moneda funcional EUR, divisa USD,
tipo 1,0850, asiento de venta en USD, histórico sellado y consulta por asiento.
"""

from __future__ import annotations


def test_quickstart_flujo_venta_usd(forex_client):
    fx = forex_client

    # 1. Divisas: USD ya sembrada por el fixture como divisa no funcional
    divisas = fx.get(10, "/api/v1/divisas")
    assert divisas.status_code == 200
    usd = {d["codigo_iso"]: d for d in divisas.json()["items"]}["USD"]

    # 2. Registramos el tipo de cambio y comprobamos que queda sellado tras asentar
    tipo = fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    assert tipo.status_code == 201

    # 3. Asiento de venta en USD: cargamos Debe/Haber en divisa
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        fecha="2026-10-01",
        divisa_id=usd["id"],
        concepto="Venta en USD",
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "1000.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "1000.0000"},
        ],
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["divisa"] == "USD"
    assert cuerpo["importe_total_divisa"] == "1000.0000"
    assert cuerpo["importe_total_funcional"] == "1085.0000"
    assert cuerpo["sellado"] is True
    assert cuerpo["usos_posteados"] == 1

    # 4. Historial de la empresa: el tipo usado aparece sellado
    tipos = fx.get(10, "/api/v1/tipos-cambio")
    assert tipos.json()["total"] == 1
    item = tipos.json()["items"][0]
    assert item["fecha"] == "2026-10-01"
    assert item["ratio"] == "1.08500000"
    assert item["sellado"] is True

    # 5. Consulta por asiento: devuelve el mismo tipo sellado
    historial = fx.get(10, "/api/v1/tipos-cambio/historial",
                       asiento_id=cuerpo["asiento_id"])
    assert historial.status_code == 200
    assert historial.json()["items"][0]["ratio"] == "1.08500000"

    # 6. Detalle del asiento en divisa: totales y sellado del tipo
    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}")
    assert detalle.status_code == 200
    d = detalle.json()
    assert d["total_divisa"] == "1000.0000"
    assert d["total_funcional"] == "1085.0000"
    assert d["sellado"] is True