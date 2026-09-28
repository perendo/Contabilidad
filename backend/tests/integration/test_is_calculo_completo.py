from tests.unit.is_support import agregar_ajuste, crear_calculo


def test_flujo_http_calculo_is_completo(is_client):
    api = is_client
    calculo = crear_calculo(api)
    positivo = agregar_ajuste(
        api,
        calculo["id"],
        tipo="AJUSTE_POSITIVO",
        importe="12000.0000",
    )
    dedaccion = agregar_ajuste(
        api,
        calculo["id"],
        tipo="DEDUCCION",
        importe="8000.0000",
    )

    recalculado = api.post(
        f"/api/v1/fiscal/is/calculos/{calculo['id']}/recalcular",
        json={"ajustes": [], "deducciones": []},
    )
    assert recalculado.status_code == 200, recalculado.text
    assert recalculado.json()["base_imponible"] == "112000.0000"
    assert recalculado.json()["cuota_diferencial"] == "0.0000"

    detalle = api.get(
        10, f"/api/v1/fiscal/is/calculos/{calculo['id']}"
    )
    assert detalle.status_code == 200
    assert len(detalle.json()["ajustes"]) == 2

    listado = api.get(
        10,
        "/api/v1/fiscal/is/calculos",
        ejercicio=2025,
        provisional=False,
        estado="calculado",
    )
    assert listado.status_code == 200
    assert listado.json()["total"] == 1
    assert listado.json()["items"][0]["id"] == calculo["id"]

    ajustes = api.get(
        10, f"/api/v1/fiscal/is/calculos/{calculo['id']}/ajustes"
    )
    assert {item["id"] for item in ajustes.json()} == {
        positivo["id"],
        dedaccion["id"],
    }

    config = api.get(10, "/api/v1/fiscal/configuracion")
    assert config.status_code == 200
    assert config.json()["tipo_is"] == "25.00"
    config_update = api.patch(
        "/api/v1/fiscal/configuracion",
        empresa_id=10,
        json={
            "tipo_is": "25.00",
            "fecha_vigencia_desde": "2000-01-01",
            "fecha_vigencia_hasta": None,
        },
    )
    assert config_update.status_code == 200
    assert config_update.json()["fecha_vigencia_desde"] == "2000-01-01"

    abierto = api.post(
        "/api/v1/fiscal/is/calculos",
        empresa_id=10,
        json={"ejercicio": 2026, "provisional": False},
    )
    assert abierto.status_code == 409
    assert abierto.json()["detail"]["code"] == "ejercicio_no_cerrado"
