from decimal import Decimal

from tests.unit.is_support import agregar_ajuste, crear_calculo


def test_calculo_is_completo(is_client):
    api = is_client
    calculo = crear_calculo(api)
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="AJUSTE_POSITIVO",
        importe="12000.0000",
    )
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="DEDUCCION",
        importe="8000.0000",
    )

    detalle = api.get(
        10, f"/api/v1/fiscal/is/calculos/{calculo['id']}"
    ).json()

    assert detalle["resultado_contable"] == "100000.0000"
    assert detalle["ajustes_positivos"] == "12000.0000"
    assert detalle["base_imponible"] == "112000.0000"
    assert detalle["tipo_impositivo"] == "25.00"
    assert detalle["cuota_integra"] == "28000.0000"
    assert detalle["deducciones"] == "8000.0000"
    assert detalle["cuota_liquida"] == "20000.0000"
    assert detalle["pagos_a_cuenta"] == "20000.0000"
    assert detalle["cuota_diferencial"] == "0.0000"
    assert Decimal(detalle["cuota_diferencial"]) == 0
