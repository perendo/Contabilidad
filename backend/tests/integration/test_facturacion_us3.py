"""Tests de integración US3 de facturación (SPEC-007): series CRUD, estados,
borrado de borradores y reserva de numeración."""

from __future__ import annotations


def test_crear_y_listar_series(facturacion_client) -> None:
    fac = facturacion_client
    r = fac.crear_serie(codigo="Z", prefijo="Z", nombre="Serie Z")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["codigo"] == "Z"
    assert data["estado"] == "activa"
    assert data["correlativo_ejemplo"] == "Z1"

    series = fac.client.get(
        "/api/v1/facturacion/series", headers=fac.headers(10)
    ).json()
    codigos = {s["codigo"] for s in series}
    assert {"S10", "Z"} <= codigos


def test_serie_duplicada_rechazada(facturacion_client) -> None:
    fac = facturacion_client
    assert fac.crear_serie(codigo="D").status_code == 201
    r = fac.crear_serie(codigo="D")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "serie_duplicada"


def test_cambiar_estado_serie(facturacion_client) -> None:
    fac = facturacion_client
    serie = fac.crear_serie(codigo="E").json()["id"]
    assert fac.estado_serie(serie, False).json()["estado"] == "inactiva"
    assert fac.estado_serie(serie, True).json()["estado"] == "activa"


def test_estado_serie_ajena_404(facturacion_client) -> None:
    fac = facturacion_client
    r = fac.estado_serie(fac.series[10], False, empresa_id=20)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "serie_no_encontrada"


def test_eliminar_factura_borrador(facturacion_client) -> None:
    fac = facturacion_client
    factura_id = fac.crear().json()["id"]
    assert fac.eliminar(factura_id).status_code == 204
    assert fac.detalle(factura_id).status_code == 404


def test_eliminar_factura_emitida_rechazado(facturacion_client) -> None:
    fac = facturacion_client
    factura_id = fac.crear().json()["id"]
    fac.emitir(factura_id)
    r = fac.eliminar(factura_id)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "estado_invalido"


def test_numeros_reservados_tras_anulacion(facturacion_client) -> None:
    fac = facturacion_client
    serie_r = fac.crear_serie(codigo="R", prefijo="R").json()["id"]
    id1 = fac.crear().json()["id"]
    assert fac.emitir(id1).json()["numero_int"] == 1
    fac.rectificar(id1, serie_id=serie_r)
    fac.anular(id1)

    id2 = fac.crear().json()["id"]
    assert fac.emitir(id2).json()["numero_int"] == 2


def test_serie_reactivada_permite_emitir(facturacion_client) -> None:
    fac = facturacion_client
    serie = fac.crear_serie(codigo="F", prefijo="F").json()["id"]
    fac.estado_serie(serie, False)
    factura_id = fac.crear(serie_id=serie).json()["id"]
    assert fac.emitir(factura_id).status_code == 409

    fac.estado_serie(serie, True)
    assert fac.emitir(factura_id).json()["numero"] == "F1"


def test_series_multi_tenant_aisladas(facturacion_client) -> None:
    fac = facturacion_client
    fac.crear_serie(codigo="A1", empresa_id=10)
    b_codigos = {
        s["codigo"]
        for s in fac.client.get(
            "/api/v1/facturacion/series", headers=fac.headers(20)
        ).json()
    }
    assert "A1" not in b_codigos
    assert "S20" in b_codigos