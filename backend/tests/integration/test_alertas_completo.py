"""Alertas de liquidez de extremo a extremo (T038, US3).

Reproduce el escenario 3 del quickstart: generar una prevision con un dia
negativo, ver la alerta, atenderla reprogramando el pago, **regenerar** la
prevision y comprobar que el bucket ya no es negativo.
"""

from __future__ import annotations

from decimal import Decimal

EJERCICIO = 2026
DESDE = "2026-09-16"
HASTA = "2026-10-31"


def _prevision_con_deficit(cf, **kwargs) -> dict:
    cuerpo = {
        "desde_fecha": DESDE,
        "hasta_fecha": HASTA,
        "granularidad": "dia",
        "movimientos_manuales": [
            {
                "tipo": "pago",
                "importe": "3000.0000",
                "fecha_prevista": "2026-09-16",
                "frecuencia": "unico",
                "concepto": "Alquiler oficinas",
            }
        ],
    }
    cuerpo.update(kwargs)
    respuesta = cf.post("/api/v1/tesoreria/previsiones", cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


# --- Escenario 3, paso 1: la alerta existe -----------------------------------


def test_generar_prevision_con_deficit_abre_alertas(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_deficit(cf)
    assert creada["n_alertas"] > 0
    assert creada["saldo_final"] == "-3000.0000"

    alertas = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()
    assert alertas["total"] == creada["n_alertas"]
    primera = alertas["items"][0]
    assert primera["fecha"] == "2026-09-16"
    assert primera["saldo_proyectado"] == "-3000.0000"
    assert primera["importe_deficit"] == "3000.0000"
    assert primera["accion_sugerida"] == "reprogramar_pago"
    assert primera["movimiento_origen_id"] is not None

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{creada['id']}").json()
    marcadas = [b for b in detalle["buckets"] if b["alerta"]]
    assert len(marcadas) == creada["n_alertas"]


def test_saldo_cero_no_aparece_como_alerta(cashflow_client):
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": DESDE,
            "hasta_fecha": "2026-09-18",
            "granularidad": "dia",
            "movimientos_manuales": [
                {"tipo": "cobro", "importe": "1000.0000", "fecha_prevista": "2026-09-16"},
                {"tipo": "pago", "importe": "1000.0000", "fecha_prevista": "2026-09-17"},
            ],
        },
    ).json()
    assert creada["n_alertas"] == 0
    assert creada["saldo_final"] == "0.0000"
    assert cf.get("/api/v1/tesoreria/alertas").json()["total"] == 0

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{creada['id']}").json()
    assert detalle["buckets"][1]["saldo_acumulado"] == "0.0000"
    assert detalle["buckets"][1]["alerta"] is False


# --- Escenario 3, paso 2: atender reprogramando ------------------------------


def test_atender_reprogramando_el_pago(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]

    respuesta = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta['id']}/atender",
        {
            "accion": "reprogramar_pago",
            "movimiento_id": alerta["movimiento_origen_id"],
            "nueva_fecha": "2026-10-15",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "atendida"
    assert cuerpo["movimiento_id"] == alerta["movimiento_origen_id"]

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{creada['id']}").json()
    movimiento = next(
        m for m in detalle["movimientos"] if m["id"] == alerta["movimiento_origen_id"]
    )
    assert movimiento["fecha_prevista"] == "2026-10-15"

    abiertas = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()
    assert abierta_para(alerta, abiertas) is False


def abierta_para(alerta: dict, listado: dict) -> bool:
    return alerta["id"] in [a["id"] for a in listado["items"]]


# --- Escenario 3, paso 3: regenerar y el deficit desaparece ------------------


def test_regenerar_despues_de_reprogramar_eleva_el_bucket(cashflow_client):
    """Escenario 3 paso 3: reprogramar el pago al dia del cobro deja de haber deficit."""
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": DESDE,
            "hasta_fecha": HASTA,
            "granularidad": "dia",
            "movimientos_manuales": [
                {
                    "tipo": "pago",
                    "importe": "3000.0000",
                    "fecha_prevista": "2026-09-16",
                    "concepto": "Alquiler oficinas",
                },
                {
                    "tipo": "cobro",
                    "importe": "3000.0000",
                    "fecha_prevista": "2026-10-20",
                    "concepto": "Cobro previsto",
                },
            ],
        },
    ).json()
    # El cobro del 20/10 compensa el pago: el deficit dura hasta el 19/10.
    assert creada["saldo_final"] == "0.0000"
    assert creada["n_alertas"] > 0

    primera = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]
    cf.post(
        f"/api/v1/tesoreria/alertas/{primera['id']}/atender",
        {
            "accion": "reprogramar_pago",
            "movimiento_id": primera["movimiento_origen_id"],
            "nueva_fecha": "2026-10-20",
        },
    )
    regenerada = cf.post(f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar", {})
    assert regenerada.status_code == 200, regenerada.text
    cuerpo = regenerada.json()
    # El plan manual se conserva con la nueva fecha: el dia 16 ya no se défice.
    assert cuerpo["n_movimientos"] == 2
    assert cuerpo["n_alertas"] == 0
    assert cuerpo["saldo_final"] == "0.0000"

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{creada['id']}").json()
    por_fecha = {b["fecha"]: b for b in detalle["buckets"]}
    assert por_fecha["2026-09-16"]["pagos"] == "0.0000"
    assert por_fecha["2026-09-16"]["saldo_acumulado"] == "0.0000"
    assert por_fecha["2026-09-16"]["alerta"] is False
    assert por_fecha["2026-10-20"]["pagos"] == "3000.0000"
    assert por_fecha["2026-10-20"]["saldo_acumulado"] == "0.0000"
    assert por_fecha["2026-10-20"]["alerta"] is False
    assert all(not b["alerta"] for b in detalle["buckets"])


def test_atender_con_incluir_ingreso_cubre_el_deficit(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]

    respuesta = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta['id']}/atender",
        {"accion": "incluir_ingreso"},
    )
    assert respuesta.status_code == 200, respuesta.text

    regenerada = cf.post(f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar", {}).json()
    assert regenerada["n_movimientos"] == 2
    # El ingreso previsto compensa el pago: ningun periodo queda en negativo.
    assert regenerada["n_alertas"] == 0
    assert regenerada["saldo_final"] == "0.0000"


def test_ignorar_la_alerta_no_toca_los_movimientos(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]

    respuesta = cf.post(f"/api/v1/tesoreria/alertas/{alerta['id']}/ignorar")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "ignorada"

    ignoradas = cf.get("/api/v1/tesoreria/alertas", estado="ignorada").json()
    assert ignoradas["total"] == 1
    abiertas = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()
    assert len(abiertas["items"]) == creada["n_alertas"] - 1

    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{creada['id']}").json()
    assert detalle["saldo_final"] == "-3000.0000"


# --- Estados terminales y validaciones --------------------------------------


def test_atender_dos_veces_devuelve_409(cashflow_client):
    cf = cashflow_client
    _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]
    cuerpo = {
        "accion": "reprogramar_pago",
        "movimiento_id": alerta["movimiento_origen_id"],
        "nueva_fecha": "2026-10-15",
    }
    assert cf.post(f"/api/v1/tesoreria/alertas/{alerta['id']}/atender", cuerpo).status_code == 200
    repetida = cf.post(f"/api/v1/tesoreria/alertas/{alerta['id']}/atender", cuerpo)
    assert repetida.status_code == 409
    assert repetida.json()["detail"]["code"] == "alerta_ya_resuelta"


def test_ignorar_una_alerta_atendida_devuelve_409(cashflow_client):
    cf = cashflow_client
    _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]
    cf.post(f"/api/v1/tesoreria/alertas/{alerta['id']}/atender", {"accion": "incluir_ingreso"})
    repetida = cf.post(f"/api/v1/tesoreria/alertas/{alerta['id']}/ignorar")
    assert repetida.status_code == 409
    assert repetida.json()["detail"]["code"] == "alerta_ya_resuelta"


def test_atender_alerta_inexistente_devuelve_404(cashflow_client):
    respuesta = cashflow_client.post(
        "/api/v1/tesoreria/alertas/11111111-1111-1111-1111-111111111111/atender",
        {"accion": "incluir_ingreso"},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "alerta_no_encontrada"


def test_reprogramar_sin_fecha_devuelve_422(cashflow_client):
    cf = cashflow_client
    _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]
    respuesta = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta['id']}/atender",
        {"accion": "reprogramar_pago", "movimiento_id": alerta["movimiento_origen_id"]},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "fecha_requerida"


def test_accion_invalida_devuelve_422(cashflow_client):
    cf = cashflow_client
    _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", estado="abierta").json()["items"][0]
    respuesta = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta['id']}/atender", {"accion": "ampliar_linea"}
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "accion_invalida"


def test_estado_invalido_en_el_filtro_devuelve_422(cashflow_client):
    respuesta = cashflow_client.get("/api/v1/tesoreria/alertas", estado="urgente")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "estado_invalido"


def test_alertas_filtradas_por_prevision(cashflow_client):
    cf = cashflow_client
    primera = _prevision_con_deficit(cf)
    segunda = _prevision_con_deficit(cf)
    todas = cf.get("/api/v1/tesoreria/alertas").json()
    assert todas["total"] == primera["n_alertas"] + segunda["n_alertas"]
    de_una = cf.get(
        "/api/v1/tesoreria/alertas", prevision_id=primera["id"]
    ).json()
    assert de_una["total"] == primera["n_alertas"]


def test_importe_del_alerta_con_cuatro_decimales(cashflow_client):
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": DESDE,
            "hasta_fecha": "2026-09-16",
            "granularidad": "dia",
            "movimientos_manuales": [
                {"tipo": "pago", "importe": "1234.5678", "fecha_prevista": "2026-09-16"}
            ],
        },
    ).json()
    alerta = cf.get("/api/v1/tesoreria/alertas").json()["items"][0]
    assert alerta["importe_deficit"] == "1234.5678"
    assert alerta["saldo_proyectado"] == "-1234.5678"
    assert Decimal(alerta["importe_deficit"]) == -Decimal(alerta["saldo_proyectado"])
    assert creada["saldo_final"] == "-1234.5678"


def test_read_only_no_puede_atender_una_alerta(cashflow_client):
    cf = cashflow_client
    _prevision_con_deficit(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas").json()["items"][0]
    assert cf.get("/api/v1/tesoreria/alertas", token_key="readonly").status_code == 200
    respuesta = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta['id']}/atender",
        {"accion": "incluir_ingreso"},
        token_key="readonly",
    )
    assert respuesta.status_code == 403
