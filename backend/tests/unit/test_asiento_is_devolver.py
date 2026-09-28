from decimal import Decimal

from tests.unit.is_support import (
    agregar_ajuste,
    contabilizar,
    crear_calculo,
    obtener_lineas,
    sumas_lineas,
)


def test_asiento_is_a_devolver_630_4709_473(is_client):
    api = is_client
    calculo = crear_calculo(api)
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="DEDUCCION",
        importe="8000.0000",
    )
    asiento_id = contabilizar(api, calculo["id"])["asiento_id"]
    lineas = obtener_lineas(api, asiento_id)

    debe, haber = sumas_lineas(lineas)
    assert debe == haber == Decimal("20000.0000")
    cuentas = {
        linea.cuenta: (linea.debe, linea.haber)
        for linea in lineas
    }
    assert cuentas["6300"] == (Decimal("17000.0000"), Decimal("0.0000"))
    assert cuentas["4709"] == (Decimal("3000.0000"), Decimal("0.0000"))
    assert cuentas["4730"] == (Decimal("0.0000"), Decimal("20000.0000"))
