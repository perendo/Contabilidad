"""Cuadre doble moneda (SPEC-016 T013).

Todo asiento en divisa cuadra en divisa Y en funcional (constitución I); el
desbalance en divisa es rechazado por el backend (nunca en la UI).
"""

from __future__ import annotations

from decimal import Decimal


def test_cuadre_exacto_divisa_y_funcional(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=10)
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["importe_total_divisa"] == "1000.0000"
    assert cuerpo["importe_total_funcional"] == "1085.0000"
    assert cuerpo["linea_redondeo"] is None

    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}")
    assert detalle.status_code == 200
    data = detalle.json()
    debe_div = sum(
        Decimal(l["debe_divisa"]) for l in data["lineas"]
    )
    haber_div = sum(
        Decimal(l["haber_divisa"]) for l in data["lineas"]
    )
    debe_fun = sum(Decimal(l["debe_funcional"]) for l in data["lineas"])
    haber_fun = sum(Decimal(l["haber_funcional"]) for l in data["lineas"])
    assert debe_div == haber_div == Decimal("1000.0000")
    assert debe_fun == haber_fun == Decimal("1085.0000")


def test_cuadre_con_varias_lineas(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.28500000")
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "600.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["4300"], "debe_divisa": "400.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "1000.0000"},
        ],
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["importe_total_divisa"] == "1000.0000"
    assert cuerpo["importe_total_funcional"] == "1285.0000"

    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}")
    data = detalle.json()
    debe_fun = sum(Decimal(l["debe_funcional"]) for l in data["lineas"])
    haber_fun = sum(Decimal(l["haber_funcional"]) for l in data["lineas"])
    assert debe_fun == haber_fun == Decimal("1285.0000")


def test_asiento_desbalanceado_divisa_rechazado(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "1000.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "999.0000"},
        ],
    )
    assert resp.status_code == 422
    assert "desbalance_divisa" in str(resp.json()).lower() or "Debe" in str(resp.json())


def test_requiere_debe_y_haber_positivos(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    cuentas = fx.cuentas(10)
    resp = fx.asiento_divisa(
        empresa_id=10,
        lineas=[
            {"cuenta_id": cuentas["4300"], "debe_divisa": "0.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": cuentas["5720"], "debe_divisa": "0.0000", "haber_divisa": "0.0000"},
        ],
    )
    assert resp.status_code == 422