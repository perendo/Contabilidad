from tests.unit.is_support import agregar_ajuste, crear_calculo


def test_calculo_is_con_cuota_diferencial_negativa(is_client):
    api = is_client
    calculo = crear_calculo(api)
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="DEDUCCION",
        importe="8000.0000",
    )

    detalle = api.get(
        10, f"/api/v1/fiscal/is/calculos/{calculo['id']}"
    ).json()

    assert detalle["cuota_liquida"] == "17000.0000"
    assert detalle["cuota_diferencial"] == "-3000.0000"
