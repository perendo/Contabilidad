"""Integración US1 completa (SPEC-016 T022).

Registrar asientos en divisa con tipo existente y con tipo explícito; verificar
cuadre en ambas monedas y sellado del tipo; detalle consultable con
divisa/ratio/funcional por línea.
"""

from __future__ import annotations

from decimal import Decimal


def _seleccionar_linea(data, cuenta: str):
    return next(l for l in data["lineas"] if l["cuenta"] == cuenta)


def test_asiento_completo_con_tipo_existente(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=10)
    assert resp.status_code == 201
    cuerpo = resp.json()
    asiento_id = cuerpo["asiento_id"]

    assert cuerpo["numero_asiento"] == 1
    assert cuerpo["divisa"] == "USD"
    assert cuerpo["ratio"] == "1.08500000"
    assert cuerpo["sellado"] is True
    assert cuerpo["linea_redondeo"] is None

    detalle = fx.get(10, f"/api/v1/asientos-divisa/{asiento_id}")
    assert detalle.status_code == 200
    data = detalle.json()
    assert data["total_divisa"] == "1000.0000"
    assert data["total_funcional"] == "1085.0000"
    assert data["ratio"] == "1.08500000"

    l4300 = _seleccionar_linea(data, "4300")
    l5720 = _seleccionar_linea(data, "5720")
    assert l4300["debe_divisa"] == "1000.0000"
    assert l4300["haber_divisa"] == "0.0000"
    assert l4300["debe_funcional"] == "1085.0000"
    assert l4300["haber_funcional"] == "0.0000"
    assert l5720["debe_divisa"] == "0.0000"
    assert l5720["haber_divisa"] == "1000.0000"
    assert l5720["debe_funcional"] == "0.0000"
    assert l5720["haber_funcional"] == "1085.0000"
    assert l5720["es_linea_redondeo"] is False


def test_asiento_con_tipo_explicito_crea_y_sella_tipo(forex_client):
    fx = forex_client
    resp = fx.asiento_divisa(
        empresa_id=10,
        fecha="2026-10-05",
        ratio_explicito={"ratio": "1.09000000"},
    )
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["ratio"] == "1.09000000"
    # El tipo quedó en el histórico como sellado
    tipos = fx.get(10, "/api/v1/tipos-cambio", divisa_id=fx.divisas(10)["usd"])
    items = [t for t in tipos.json()["items"] if t["fecha"] == "2026-10-05"]
    assert items and items[0]["sellado"] is True
    assert items[0]["ratio"] == "1.09000000"

    # El detalle usa el mismo ratio
    detalle = fx.get(10, f"/api/v1/asientos-divisa/{cuerpo['asiento_id']}")
    assert detalle.json()["ratio"] == "1.09000000"
    assert detalle.json()["total_funcional"] == "1090.0000"


def test_detalle_con_varias_lineas_suma_ambas_monedas(forex_client):
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
    detalle = fx.get(10, f"/api/v1/asientos-divisa/{resp.json()['asiento_id']}")
    data = detalle.json()
    assert len(data["lineas"]) == 3
    func_debe = sum(Decimal(l["debe_funcional"]) for l in data["lineas"])
    func_haber = sum(Decimal(l["haber_funcional"]) for l in data["lineas"])
    assert func_debe == func_haber == Decimal("1285.0000")