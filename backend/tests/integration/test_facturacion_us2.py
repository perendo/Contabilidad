"""Tests de integración US2 de facturación (SPEC-007): rectificativas (abono),
asiento REVERSAL invertido, inmutabilidad del original, anulación y aislamiento."""

from __future__ import annotations


def _emitida(fac, empresa_id: int = 10, **kwargs):
    factura_id = fac.crear(empresa_id=empresa_id, **kwargs).json()["id"]
    r = fac.emitir(factura_id, empresa_id=empresa_id)
    assert r.status_code == 200, r.text
    return factura_id, r.json()


def test_rectificar_genera_abono_con_numero_propio(facturacion_client) -> None:
    fac = facturacion_client
    original_id, original = _emitida(fac)
    serie_r = fac.crear_serie(codigo="R", prefijo="R").json()["id"]

    r = fac.rectificar(original_id, serie_id=serie_r, motivo="Devolución")
    assert r.status_code == 201, r.text
    abono = r.json()
    assert abono["tipo"] == "RECTIFICATIVA"
    assert abono["estado"] == "emitida"
    assert abono["numero"] == "R1"
    assert abono["factura_original_id"] == original_id
    assert abono["importe_total"] == original["importe_total"]
    assert abono["asiento_id"]


def test_asiento_reversal_invertido_balanceado(facturacion_client) -> None:
    fac = facturacion_client
    original_id, original = _emitida(fac)
    abono = fac.rectificar(original_id).json()

    asiento = fac.asiento(abono["asiento_id"]).json()
    assert asiento["tipo"] == "REVERSAL"
    assert asiento["asiento_original_id"] == original["asiento_id"]
    assert asiento["estado"] == "POSTED"
    assert asiento["total_debe"] == asiento["total_haber"] == "121.0000"
    cuentas = {l["cuenta"]: l for l in asiento["lineas"]}
    assert cuentas["4300"]["haber"] == "121.0000"
    assert cuentas["7000"]["debe"] == "100.0000"
    assert cuentas["4770"]["debe"] == "21.0000"


def test_original_intacto_tras_rectificar(facturacion_client) -> None:
    fac = facturacion_client
    original_id, original = _emitida(fac)
    antes = fac.asiento(original["asiento_id"]).json()

    fac.rectificar(original_id)

    despues = fac.detalle(original_id).json()
    assert despues["estado"] == "emitida"
    assert despues["asiento_id"] == original["asiento_id"]
    assert despues["importe_total"] == "121.0000"
    asiento = fac.asiento(original["asiento_id"]).json()
    assert asiento["estado"] == "POSTED"
    assert asiento["total_debe"] == antes["total_debe"]
    assert asiento["total_haber"] == antes["total_haber"]
    assert {l["cuenta"]: l["debe"] for l in asiento["lineas"]} == {
        l["cuenta"]: l["debe"] for l in antes["lineas"]
    }


def test_rectificacion_parcial(facturacion_client) -> None:
    fac = facturacion_client
    original_id, _ = _emitida(fac)
    abono = fac.rectificar(
        original_id, lineas=[fac.linea(precio="50.0000")]
    ).json()
    assert abono["importe_base"] == "50.0000"
    assert abono["importe_total"] == "60.5000"

    asiento = fac.asiento(abono["asiento_id"]).json()
    assert asiento["total_debe"] == asiento["total_haber"] == "60.5000"
    cuentas = {l["cuenta"]: l for l in asiento["lineas"]}
    assert cuentas["4300"]["haber"] == "60.5000"
    assert cuentas["7000"]["debe"] == "50.0000"
    assert cuentas["4770"]["debe"] == "10.5000"


def test_rectificar_borrador_rechazado(facturacion_client) -> None:
    fac = facturacion_client
    factura_id = fac.crear().json()["id"]
    r = fac.rectificar(factura_id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "estado_invalido"


def test_anular_requiere_rectificativa(facturacion_client) -> None:
    fac = facturacion_client
    original_id, _ = _emitida(fac)
    r = fac.anular(original_id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "sin_rectificativa"


def test_anular_tras_rectificativa(facturacion_client) -> None:
    fac = facturacion_client
    original_id, _ = _emitida(fac)
    fac.rectificar(original_id)
    r = fac.anular(original_id)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "anulada"
    assert fac.detalle(original_id).json()["estado"] == "anulada"


def test_rectificacion_multi_tenant(facturacion_client) -> None:
    fac = facturacion_client
    original_id, _ = _emitida(fac, empresa_id=10)
    assert fac.rectificar(original_id, empresa_id=20).status_code == 404

    abono = fac.rectificar(original_id, empresa_id=10).json()
    assert fac.detalle(abono["id"], empresa_id=20).status_code == 404
    assert fac.listar(empresa_id=20).json()["total"] == 0
    assert fac.listar(empresa_id=10).json()["total"] == 2