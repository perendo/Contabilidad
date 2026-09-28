from decimal import Decimal

from models.fiscal.calculo_is import EstadoCalculoIS
from tests.unit.is_support import (
    contabilizar,
    crear_calculo,
    obtener_calculo,
    obtener_lineas,
    sumas_lineas,
)


def test_contabilizacion_is_http_y_asiento_posted(is_client):
    api = is_client
    calculo = crear_calculo(api)
    response = contabilizar(api, calculo["id"])

    assert response["estado"] == "contabilizado"
    assert response["asiento_id"]
    persistido = obtener_calculo(api, calculo["id"])
    assert persistido.estado == EstadoCalculoIS.contabilizado
    lineas = obtener_lineas(api, response["asiento_id"])
    debe, haber = sumas_lineas(lineas)
    assert debe == haber == Decimal("25000.0000")
    assert all(
        linea.debe == Decimal("0.0000")
        or linea.haber == Decimal("0.0000")
        for linea in lineas
    )

    duplicado = api.post(
        f"/api/v1/fiscal/is/calculos/{calculo['id']}/contabilizar",
        json={"fecha_asiento": "2025-12-31"},
    )
    assert duplicado.status_code == 409
    assert duplicado.json()["detail"]["code"] == "estado_invalido"

    ajuste_bloqueado = api.post(
        f"/api/v1/fiscal/is/calculos/{calculo['id']}/ajustes",
        json={
            "tipo": "DEDUCCION",
            "descripcion": "Tarde",
            "importe": "1.0000",
        },
    )
    assert ajuste_bloqueado.status_code == 409
    assert ajuste_bloqueado.json()["detail"]["code"] == "calculo_contabilizado"
