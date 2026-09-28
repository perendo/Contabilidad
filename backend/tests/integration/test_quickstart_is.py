from decimal import Decimal

from tests.unit.is_support import (
    agregar_ajuste,
    contabilizar,
    crear_calculo,
    obtener_lineas,
    sumas_lineas,
)


def test_quickstart_is_escenarios_1_a_6(is_client):
    api = is_client
    calculo = crear_calculo(api)
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="AJUSTE_POSITIVO",
        importe="12000.0000",
        descripcion="Diferencias temporarias no deducibles",
    )
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="DEDUCCION",
        importe="8000.0000",
        descripcion="Deduccion I+D",
    )
    recalculo = api.post(
        f"/api/v1/fiscal/is/calculos/{calculo['id']}/recalcular",
        json={"ajustes": [], "deducciones": []},
    )
    assert recalculo.status_code == 200
    assert recalculo.json()["base_imponible"] == "112000.0000"
    assert recalculo.json()["cuota_liquida"] == "20000.0000"
    assert recalculo.json()["cuota_diferencial"] == "0.0000"

    contabilizacion = contabilizar(api, calculo["id"])
    debe, haber = sumas_lineas(
        obtener_lineas(api, contabilizacion["asiento_id"])
    )
    assert debe == haber == Decimal("20000.0000")

    modelo = api.post(
        "/api/v1/fiscal/is/modelo-200",
        empresa_id=10,
        json={"calculo_is_id": calculo["id"]},
    )
    assert modelo.status_code == 201
    descarga = api.get(
        10, f"/api/v1/fiscal/is/modelo-200/{modelo.json()['id']}"
    )
    assert descarga.status_code == 200
    assert "text/csv" in descarga.headers["content-type"]

    provisional = crear_calculo(api, provisional=True, ejercicio=2026)
    provisional_recalculo = api.post(
        f"/api/v1/fiscal/is/calculos/{provisional['id']}/recalcular",
        json={
            "ajustes": [
                {
                    "tipo": "AJUSTE_POSITIVO",
                    "descripcion": "Estimacion",
                    "importe": "5000.0000",
                }
            ],
            "deducciones": [],
        },
    )
    assert provisional_recalculo.status_code == 200
    assert provisional_recalculo.json()["provisional"] is True
    assert provisional_recalculo.json()["cuota_diferencial"] == "6250.0000"

    segundo_definitivo = api.post(
        "/api/v1/fiscal/is/calculos",
        empresa_id=10,
        json={"ejercicio": 2025, "provisional": False},
    )
    assert segundo_definitivo.status_code == 409
    assert segundo_definitivo.json()["detail"]["code"] == "calculo_ya_definitivo"

    cross_tenant = api.get(
        20, f"/api/v1/fiscal/is/calculos/{calculo['id']}"
    )
    assert cross_tenant.status_code == 404
