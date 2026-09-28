from tests.unit.is_support import crear_calculo


def test_calculo_provisional_se_recalcula_y_definitivo_es_unico(is_client):
    api = is_client
    provisional = crear_calculo(api, provisional=True, ejercicio=2026)
    response = api.post(
        f"/api/v1/fiscal/is/calculos/{provisional['id']}/recalcular",
        json={
            "ajustes": [
                {
                    "tipo": "AJUSTE_POSITIVO",
                    "descripcion": "Estimacion intermedia",
                    "importe": "5000.0000",
                }
            ],
            "deducciones": [],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["provisional"] is True
    assert response.json()["base_imponible"] == "105000.0000"
    assert response.json()["cuota_integra"] == "26250.0000"
    assert response.json()["cuota_diferencial"] == "6250.0000"

    definitivo = crear_calculo(api)
    segundo = api.post(
        "/api/v1/fiscal/is/calculos",
        json={"ejercicio": 2025, "provisional": False},
    )
    assert segundo.status_code == 409
    assert segundo.json()["detail"]["code"] == "calculo_ya_definitivo"
    assert definitivo["provisional"] is False


def test_calculo_definitivo_requiere_ejercicio_cerrado(is_client):
    response = is_client.post(
        "/api/v1/fiscal/is/calculos",
        json={"ejercicio": 2026, "provisional": False},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ejercicio_no_cerrado"
