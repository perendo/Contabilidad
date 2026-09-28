from tests.unit.is_support import crear_calculo


def test_calculo_is_con_cuota_diferencial_positiva(is_client):
    calculo = crear_calculo(is_client)

    assert calculo["resultado_contable"] == "100000.0000"
    assert calculo["pagos_a_cuenta"] == "20000.0000"
    assert calculo["cuota_liquida"] == "25000.0000"
    assert calculo["cuota_diferencial"] == "5000.0000"
