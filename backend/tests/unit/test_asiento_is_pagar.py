from decimal import Decimal

from tests.unit.is_support import (
    contabilizar,
    crear_calculo,
    obtener_lineas,
    sumas_lineas,
)


def test_asiento_is_a_pagar_630_473_4752(is_client):
    calculo = crear_calculo(is_client)
    asiento_id = contabilizar(is_client, calculo["id"])["asiento_id"]
    lineas = obtener_lineas(is_client, asiento_id)

    debe, haber = sumas_lineas(lineas)
    assert debe == haber == Decimal("25000.0000")
    assert all(linea.debe == 0 or linea.haber == 0 for linea in lineas)
    cuentas = {
        linea.cuenta: (linea.debe, linea.haber)
        for linea in lineas
    }
    assert cuentas["6300"] == (Decimal("25000.0000"), Decimal("0.0000"))
    assert cuentas["4730"] == (Decimal("0.0000"), Decimal("20000.0000"))
    assert cuentas["4752"] == (Decimal("0.0000"), Decimal("5000.0000"))
