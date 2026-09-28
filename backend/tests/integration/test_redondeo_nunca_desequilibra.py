"""Batería de redondeo: nunca se desequilibra la moneda funcional (SPEC-016 T047).

Cuadre divisa intacto y cuadre funcional garantizado por la línea de redondeo
6680/7690 (constitución I). Casos verificados numéricamente.
"""

from __future__ import annotations

from decimal import Decimal


def test_redondeo_1_3_debe_linea_6680(forex_client):
    fx = forex_client
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        fecha="2026-10-01",
        ratio_explicito={"ratio": "0.33333333"},
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "1.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["4300"], "debe_divisa": "1.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["4300"], "debe_divisa": "1.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "3.0000"},
        ],
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["importe_total_divisa"] == "3.0000"
    # 0,9999 vs 1,0000 funcional: remanente 0,0001 -> Debe 6680
    assert cuerpo["linea_redondeo"] is not None
    assert cuerpo["linea_redondeo"]["cuenta"] == "6680"
    assert cuerpo["linea_redondeo"]["importe"] == "0.0001"

    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}").json()
    redondeo = [l for l in detalle["lineas"] if l["es_linea_redondeo"]]
    assert len(redondeo) == 1
    assert redondeo[0]["cuenta"] == "6680"
    assert redondeo[0]["debe"] == "0.0001"
    # Debe == Haber funcional
    debe = sum(Decimal(l["debe"]) for l in detalle["lineas"])
    haber = sum(Decimal(l["haber"]) for l in detalle["lineas"])
    assert debe == haber == Decimal("1.0000")


def test_redondeo_1_3_haber_linea_7690(forex_client):
    fx = forex_client
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        fecha="2026-10-01",
        ratio_explicito={"ratio": "0.33333333"},
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "3.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "1.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "1.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "1.0000"},
        ],
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["importe_total_divisa"] == "3.0000"
    # 1,0000 vs 0,9999 funcional: remanente 0,0001 -> Haber 7690
    assert cuerpo["linea_redondeo"] is not None
    assert cuerpo["linea_redondeo"]["cuenta"] == "7690"
    assert cuerpo["linea_redondeo"]["importe"] == "0.0001"

    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}").json()
    redondeo = [l for l in detalle["lineas"] if l["es_linea_redondeo"]]
    assert len(redondeo) == 1
    assert redondeo[0]["cuenta"] == "7690"
    assert redondeo[0]["haber"] == "0.0001"


def test_redondeo_1687_lineas(forex_client):
    """Cuadre funcional con dos contrapartidas distintas y redondeo mínimo."""
    fx = forex_client
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        fecha="2026-10-01",
        ratio_explicito={"ratio": "0.16666667"},
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "2.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["4300"], "debe_divisa": "2.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "4.0000"},
        ],
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}").json()
    debe = sum(Decimal(l["debe"]) for l in detalle["lineas"])
    haber = sum(Decimal(l["haber"]) for l in detalle["lineas"])
    assert debe == haber


def test_sin_redondeo_cuando_no_hay_remanente(forex_client):
    """Ratio con producto exacto a 4 decimales no genera línea de redondeo."""
    fx = forex_client
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        fecha="2026-10-01",
        ratio_explicito={"ratio": "1.08500000"},
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "1000.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "1000.0000"},
        ],
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["linea_redondeo"] is None
    assert cuerpo["importe_total_funcional"] == "1085.0000"

    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}").json()
    assert detalle["lineas"][0]["es_linea_redondeo"] is False
    assert not any(l["es_linea_redondeo"] for l in detalle["lineas"])