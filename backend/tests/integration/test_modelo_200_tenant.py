from tests.unit.is_support import contabilizar, crear_calculo


def test_modelo_200_aislado_por_empresa(is_client):
    api = is_client
    calculo = crear_calculo(api)
    contabilizar(api, calculo["id"])
    generado = api.post(
        "/api/v1/fiscal/is/modelo-200",
        empresa_id=10,
        json={"calculo_is_id": calculo["id"]},
    )
    assert generado.status_code == 201
    modelo_id = generado.json()["id"]

    descarga = api.get(
        20, f"/api/v1/fiscal/is/modelo-200/{modelo_id}"
    )
    assert descarga.status_code == 404
    assert descarga.json()["detail"]["code"] == "modelo_no_encontrado"

    generacion = api.post(
        "/api/v1/fiscal/is/modelo-200",
        empresa_id=20,
        json={"calculo_is_id": calculo["id"]},
    )
    assert generacion.status_code == 404
    assert generacion.json()["detail"]["code"] == "calculo_no_encontrado"

    listado = api.get(20, "/api/v1/fiscal/is/modelo-200", ejercicio=2025)
    assert listado.status_code == 200
    assert listado.json() == {"items": [], "total": 0}
