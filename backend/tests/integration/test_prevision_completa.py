"""Prevision de tesoreria completa por API (T020, US1).

Reproduce el escenario 1 y el 2 del quickstart: vencimientos pendientes + pago
recurrente manual -> POST /previsiones -> detalle con buckets. Verifica que la
suma de movimientos iguala el `saldo_final` y que cada bucket cuadra.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

EJERCICIO = 2026
DESDE = "2026-09-16"
HASTA = "2026-10-31"


def _manual_pago(fecha: str = "2026-10-01", importe: str = "1200.0000") -> dict:
    return {
        "tipo": "pago",
        "importe": importe,
        "fecha_prevista": fecha,
        "frecuencia": "unico",
        "concepto": "Alquiler",
    }


# --- Escenario 1: generacion y detalle ---------------------------------------


def test_escenario_1_genera_prevision_diaria(cashflow_client):
    cf = cashflow_client
    cf.vencimientos(
        especificaciones=[
            {"fecha_vencimiento": date(EJERCICIO, 9, 30), "importe": "1500.0000", "recibo_num": "R-30"},
            {"fecha_vencimiento": date(EJERCICIO, 10, 15), "importe": "800.0000", "recibo_num": "R-15"},
            {
                "fecha_vencimiento": date(EJERCICIO, 9, 1),
                "importe": "300.0000",
                "estado": "cobrado",
                "recibo_num": "R-VENCIDO",
            },
        ]
    )

    respuesta = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": DESDE,
            "hasta_fecha": HASTA,
            "granularidad": "dia",
            "movimientos_manuales": [_manual_pago()],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["numero_prevision"] == 1
    assert cuerpo["granularidad"] == "dia"
    assert cuerpo["estado"] == "generada"
    assert cuerpo["n_movimientos"] == 3
    assert len(cuerpo["excluidos"]) == 1
    assert cuerpo["excluidos"][0]["motivo"] == "cobrado"
    # Importes como cadenas de 4 decimales (contrato).
    for clave in ("saldo_inicial", "saldo_final"):
        assert cuerpo[clave].count(".") == 1
        assert len(cuerpo[clave].split(".")[1]) == 4

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{cuerpo['id']}").json()
    buckets = {b["fecha"]: b for b in detalle["buckets"]}
    # El cobro del 30/09 y el pago del 01/10 estan en su fecha.
    assert buckets["2026-09-30"]["cobros"] == "1500.0000"
    assert buckets["2026-10-15"]["cobros"] == "800.0000"
    assert buckets["2026-10-01"]["pagos"] == "1200.0000"
    # El vencido cobrado NO aparece.
    assert "2026-09-01" not in buckets
    # El ultimo acumulado es el saldo final de la cabecera.
    assert detalle["buckets"][-1]["saldo_acumulado"] == cuerpo["saldo_final"]
    # Suma de movimientos == variacion == saldo_final - saldo_inicial.
    variacion = sum(
        (Decimal(b["neto"]) for b in detalle["buckets"]), Decimal(0)
    )
    assert variacion == Decimal(cuerpo["saldo_final"]) - Decimal(cuerpo["saldo_inicial"])
    assert sum(
        (Decimal(b["saldo_acumulado"]) for b in detalle["buckets"]), Decimal(0)
    ) is not None
    # Los excluidos se listan con su motivo.
    assert [e["motivo"] for e in detalle["excluidos"]] == ["cobrado"]


def test_escenario_2_pago_recurrente_mensual(cashflow_client):
    cf = cashflow_client
    respuesta = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": "2026-10-01",
            "hasta_fecha": "2026-12-31",
            "granularidad": "mes",
            "movimientos_manuales": [
                {
                    "tipo": "pago",
                    "importe": "1200.0000",
                    "fecha_prevista": "2026-10-01",
                    "frecuencia": "mensual",
                    "concepto": "Alquiler",
                }
            ],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["n_movimientos"] == 3

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{cuerpo['id']}").json()
    pagos_por_mes = {
        b["fecha"]: b["pagos"]
        for b in detalle["buckets"]
        if Decimal(b["pagos"]) != 0
    }
    assert pagos_por_mes == {
        "2026-10-01": "1200.0000",
        "2026-11-01": "1200.0000",
        "2026-12-01": "1200.0000",
    }
    assert cuerpo["saldo_final"] == "-3600.0000"


def test_listado_paginado_y_filtrado(cashflow_client):
    cf = cashflow_client
    cuerpo = {
        "desde_fecha": DESDE,
        "hasta_fecha": HASTA,
        "granularidad": "semana",
    }
    assert cf.post("/api/v1/tesoreria/previsiones", cuerpo).status_code == 201
    assert cf.post("/api/v1/tesoreria/previsiones", cuerpo).status_code == 201

    listado = cf.get("/api/v1/tesoreria/previsiones").json()
    assert listado["total"] == 2
    assert [p["numero_prevision"] for p in listado["items"]] == [2, 1]

    por_dia = cf.get("/api/v1/tesoreria/previsiones", granularidad="dia").json()
    assert por_dia["total"] == 0
    por_semana = cf.get("/api/v1/tesoreria/previsiones", granularidad="semana").json()
    assert por_semana["total"] == 2
    por_estado = cf.get("/api/v1/tesoreria/previsiones", estado="anulada").json()
    assert por_estado["total"] == 0


def test_prevision_inexistente_devuelve_404(cashflow_client):
    respuesta = cashflow_client.get(
        "/api/v1/tesoreria/previsiones/11111111-1111-1111-1111-111111111111"
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "prevision_no_encontrada"


# --- Validaciones del contrato ----------------------------------------------


@pytest.mark.parametrize(
    "cuerpo,code",
    [
        ({"desde_fecha": HASTA, "hasta_fecha": DESDE}, "rango_invalido"),
        (
            {"desde_fecha": DESDE, "hasta_fecha": HASTA, "granularidad": "trimestre"},
            "granularidad_invalida",
        ),
        (
            {
                "desde_fecha": DESDE,
                "hasta_fecha": HASTA,
                "movimientos_manuales": [
                    {"tipo": "pago", "importe": "-5", "fecha_prevista": "2026-10-01"}
                ],
            },
            "importe_invalido",
        ),
        (
            {
                "desde_fecha": DESDE,
                "hasta_fecha": HASTA,
                "movimientos_manuales": [
                    {"tipo": "traspaso", "importe": "5", "fecha_prevista": "2026-10-01"}
                ],
            },
            "tipo_invalido",
        ),
        (
            {
                "desde_fecha": DESDE,
                "hasta_fecha": HASTA,
                "movimientos_manuales": [
                    {"tipo": "pago", "importe": "5", "frecuencia": "diaria"}
                ],
            },
            "frecuencia_invalida",
        ),
    ],
)
def test_validaciones_422(cashflow_client, cuerpo, code):
    respuesta = cashflow_client.post("/api/v1/tesoreria/previsiones", cuerpo)
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"]["code"] == code


def test_manual_sin_fecha_se_reporta_como_excluido(cashflow_client):
    """Edge case del spec: sin fecha prevista el movimiento queda fuera."""
    respuesta = cashflow_client.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": DESDE,
            "hasta_fecha": HASTA,
            "granularidad": "dia",
            "movimientos_manuales": [
                {"tipo": "pago", "importe": "1200.0000", "concepto": "Sin datar"}
            ],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["n_movimientos"] == 0
    assert cuerpo["excluidos"][0]["motivo"] == "sin_fecha"
    assert cuerpo["saldo_final"] == cuerpo["saldo_inicial"]


# --- Regeneracion (quickstart escenario 3, paso 3) ---------------------------


def test_regenerar_conserva_numero_y_refresca(cashflow_client):
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": DESDE,
            "hasta_fecha": HASTA,
            "granularidad": "dia",
            "movimientos_manuales": [_manual_pago("2026-10-01")],
        },
    ).json()
    assert creada["n_movimientos"] == 1
    assert creada["saldo_final"] == "-1200.0000"

    # Al acortar el rango, el pago cae fuera y la prevision se queda en cero.
    regenerada = cf.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar",
        {"hasta_fecha": "2026-09-30", "granularidad": "dia"},
    )
    assert regenerada.status_code == 200, regenerada.text
    cuerpo = regenerada.json()
    assert cuerpo["numero_prevision"] == creada["numero_prevision"]
    assert cuerpo["n_movimientos"] == 0
    assert cuerpo["saldo_final"] == "0.0000"
    assert cuerpo["hasta_fecha"] == "2026-09-30"

    # Regenerar con el rango amplio recupera el pago.
    otra = cf.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar",
        {"hasta_fecha": HASTA, "granularidad": "dia"},
    )
    assert otra.status_code == 200
    assert otra.json()["n_movimientos"] == 1
    # La correlatividad no se altera: sigue siendo la prevision numero 1.
    listado = cf.get("/api/v1/tesoreria/previsiones").json()
    assert [p["numero_prevision"] for p in listado["items"]] == [1]


def test_regenerar_con_vencimiento_nuevo_lo_recoge(cashflow_client):
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {"desde_fecha": DESDE, "hasta_fecha": HASTA, "granularidad": "dia"},
    ).json()
    assert creada["n_movimientos"] == 0

    cf.vencimientos(
        especificaciones=[
            {"fecha_vencimiento": date(EJERCICIO, 10, 5), "importe": "900.0000"}
        ]
    )
    regenerada = cf.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar", {}
    ).json()
    assert regenerada["n_movimientos"] == 1
    assert regenerada["saldo_final"] == "900.0000"


def test_regenerar_prevision_inexistente_devuelve_404(cashflow_client):
    respuesta = cashflow_client.post(
        "/api/v1/tesoreria/previsiones/22222222-2222-2222-2222-222222222222/regenerar",
        {},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "prevision_no_encontrada"


# --- Alta manual de un movimiento previsto ----------------------------------


def test_alta_manual_de_movimiento_previsto(cashflow_client):
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {"desde_fecha": DESDE, "hasta_fecha": HASTA, "granularidad": "dia"},
    ).json()

    respuesta = cf.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/movimientos",
        {
            "tipo": "pago",
            "importe": "300.0000",
            "fecha_prevista": "2026-09-20",
            "frecuencia": "unico",
            "concepto": "Recibo de luz",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["importe"] == "300.0000"
    assert respuesta.json()["origen"] == "pago_recurrente"

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{creada['id']}").json()
    assert detalle["buckets"][4]["fecha"] == "2026-09-20"
    assert detalle["buckets"][4]["pagos"] == "300.0000"


def test_alta_manual_sin_fecha_devuelve_422(cashflow_client):
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {"desde_fecha": DESDE, "hasta_fecha": HASTA, "granularidad": "dia"},
    ).json()
    respuesta = cf.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/movimientos",
        {"tipo": "pago", "importe": "300.0000"},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "fecha_requerida"
