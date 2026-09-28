"""Escenarios del quickstart de SPEC-027 reproducidos como tests (T042).

1. Generar la prevision por dia y ver el detalle con el vencido cobrado fuera.
2. Proyeccion mensual con un pago recurrente replicado.
3. Alerta de liquidez, atender reprogramando y regenerar sin deficit.
4. Informe EFE con los tres bloques, cuadre y formulacion con override.
5. Aislamiento multi-empresa entre listados, detalle y alertas.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

EJERCICIO = 2026
A = 10
B = 20


# --- Escenario 1: prevision diaria -------------------------------------------


def test_escenario_1_prevision_diaria(cashflow_client):
    cf = cashflow_client
    # Seed minimo del quickstart: un cobro a 30/09, un pago a 15/10, un vencido
    # ya cobrado y saldo de tesoreria inicial registrado.
    cf.plantar(empresa_id=A, code="1000", parent="100", name="Capital social")
    cf.asiento(
        empresa_id=A,
        fecha="2026-01-02",
        lineas=[
            {"cuenta": "5720", "debe": "5000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "5000.0000"},
        ],
        concepto="Saldo de tesoreria inicial",
        tipo="OPENING",
    )
    cf.vencimientos(
        empresa_id=A,
        especificaciones=[
            {"fecha_vencimiento": date(2026, 9, 30), "importe": "2000.0000"},
            {
                "fecha_vencimiento": date(2026, 10, 15),
                "importe": "900.0000",
                "tipo": "pago",
            },
            {
                "fecha_vencimiento": date(2026, 9, 1),
                "importe": "300.0000",
                "estado": "cobrado",
            },
        ],
    )

    # 1) Generar la prevision diaria.
    respuesta = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": "2026-09-16",
            "hasta_fecha": "2026-10-31",
            "granularidad": "dia",
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
        empresa_id=A,
    )
    assert respuesta.status_code == 201, respuesta.text
    creada = respuesta.json()
    assert creada["numero_prevision"] == 1
    assert creada["saldo_inicial"] == "5000.0000"
    # Con el rango del quickstart (hasta 31/10) el alquiler mensual solo cae una vez.
    assert creada["n_movimientos"] == 3
    assert [e["motivo"] for e in creada["excluidos"]] == ["cobrado"]

    # 2) Detalle con buckets, cobros, pagos y saldo acumulado.
    detalle = cf.get(
        f"/api/v1/tesoreria/previsiones/{creada['id']}", empresa_id=A
    ).json()
    por_fecha = {b["fecha"]: b for b in detalle["buckets"]}
    assert por_fecha["2026-09-30"]["cobros"] == "2000.0000"
    # El vencimiento de 15/10 es un pago, no un cobro.
    assert por_fecha["2026-10-15"]["pagos"] == "900.0000"
    assert por_fecha["2026-10-01"]["pagos"] == "1200.0000"
    # El vencido cobrado NO aparece en la proyeccion.
    assert "2026-09-01" not in por_fecha
    assert detalle["saldo_final"] == "4900.0000"
    assert por_fecha["2026-10-31"]["saldo_acumulado"] == "4900.0000"


# --- Escenario 2: proyeccion mensual y pago recurrente ----------------------


def test_escenario_2_recurrente_mensual(cashflow_client):
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
        empresa_id=A,
    )
    assert respuesta.status_code == 201, respuesta.text
    creada = respuesta.json()
    assert creada["granularidad"] == "mes"
    assert creada["n_movimientos"] == 3

    detalle = cf.get(
        f"/api/v1/tesoreria/previsiones/{creada['id']}", empresa_id=A
    ).json()
    assert [b["fecha"] for b in detalle["buckets"]] == [
        "2026-10-01",
        "2026-11-01",
        "2026-12-01",
    ]
    assert [b["pagos"] for b in detalle["buckets"]] == [
        "1200.0000",
        "1200.0000",
        "1200.0000",
    ]
    assert [b["saldo_acumulado"] for b in detalle["buckets"]] == [
        "-1200.0000",
        "-2400.0000",
        "-3600.0000",
    ]
    assert detalle["saldo_final"] == "-3600.0000"


# --- Escenario 3: alerta de liquidez ----------------------------------------


def test_escenario_3_alerta_reprogramar_y_regenerar(cashflow_client):
    cf = cashflow_client
    creada = cf.post(
        "/api/v1/tesoreria/previsiones",
        {
            "desde_fecha": "2026-09-16",
            "hasta_fecha": "2026-10-31",
            "granularidad": "dia",
            "movimientos_manuales": [
                {
                    "tipo": "pago",
                    "importe": "2000.0000",
                    "fecha_prevista": "2026-09-16",
                    "concepto": "Alquiler",
                },
                {
                    "tipo": "cobro",
                    "importe": "2000.0000",
                    "fecha_prevista": "2026-10-05",
                    "concepto": "Cobro previsto",
                },
            ],
        },
        empresa_id=A,
    ).json()

    # 1) Alertas abiertas del deficit.
    abiertas = cf.get("/api/v1/tesoreria/alertas", estado="abierta", empresa_id=A).json()
    assert abiertas["total"] > 0
    alerta = abiertas["items"][0]
    assert alerta["saldo_proyectado"] == "-2000.0000"
    assert alerta["importe_deficit"] == "2000.0000"
    assert alerta["accion_sugerida"] == "reprogramar_pago"

    # 2) Atender reprogramando el pago al dia del cobro.
    atendida = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta['id']}/atender",
        {
            "accion": "reprogramar_pago",
            "movimiento_id": alerta["movimiento_origen_id"],
            "nueva_fecha": "2026-10-05",
        },
        empresa_id=A,
    )
    assert atendida.status_code == 200, atendida.text
    assert atendida.json()["estado"] == "atendida"

    # 3) Regenerar: el bucket ya no es negativo.
    regenerada = cf.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar", {}, empresa_id=A
    ).json()
    assert regenerada["n_alertas"] == 0
    assert regenerada["saldo_final"] == "0.0000"
    detalle = cf.get(
        f"/api/v1/tesoreria/previsiones/{creada['id']}", empresa_id=A
    ).json()
    assert all(b["alerta"] is False for b in detalle["buckets"])


# --- Escenario 4: informe EFE ----------------------------------------------


def test_escenario_4_efe_tres_bloques_y_formulacion(cashflow_client):
    cf = cashflow_client
    cf.plantar(empresa_id=A, code="1000", parent="100", name="Capital social")
    cf.plantar(empresa_id=A, code="1600", parent="160", name="Prestamos a LP")
    cf.asiento(
        empresa_id=A,
        fecha="2026-01-02",
        lineas=[
            {"cuenta": "5720", "debe": "10000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "10000.0000"},
        ],
        concepto="Apertura",
        tipo="OPENING",
    )
    cf.asiento(
        empresa_id=A,
        fecha="2026-04-01",
        lineas=[
            {"cuenta": "5720", "debe": "4000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "4000.0000"},
        ],
        concepto="Ventas",
    )
    cf.asiento(
        empresa_id=A,
        fecha="2026-06-01",
        lineas=[
            {"cuenta": "2100", "debe": "1500.0000", "haber": "0"},
            {"cuenta": "5720", "debe": "0", "haber": "1500.0000"},
        ],
        concepto="Inmovilizado",
    )
    cf.asiento(
        empresa_id=A,
        fecha="2026-07-01",
        lineas=[
            {"cuenta": "5720", "debe": "2500.0000", "haber": "0"},
            {"cuenta": "1600", "debe": "0", "haber": "2500.0000"},
        ],
        concepto="Devolucion de prestamo",
    )

    # 1) Generar el EFE.
    informe = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=A).json()
    assert informe["cuadre"] is True
    assert informe["sin_conciliar"] is False
    assert informe["saldo_inicial"] == "10000.0000"
    assert informe["saldo_final"] == "15000.0000"
    assert informe["bloques"]["operativa"]["total"] == "4000.0000"
    assert informe["bloques"]["inversion"]["total"] == "-1500.0000"
    assert informe["bloques"]["financiacion"]["total"] == "2500.0000"

    # 2) Formular con override: la venta de 7000 pasa a inversion.
    cuentas = cf.cuentas(A)
    formulada = cf.post(
        "/api/v1/tesoreria/efe/formular",
        {
            "ejercicio": EJERCICIO,
            "clasificaciones": [{"cuenta_id": cuentas["7000"], "bloque": "inversion"}],
        },
        empresa_id=A,
    )
    assert formulada.status_code == 200, formulada.text
    cuerpo = formulada.json()
    assert cuerpo["estado"] == "formulado"
    assert cuerpo["cuadre"] is True
    assert cuerpo["sin_conciliar"] is False
    assert cuerpo["totales"]["operativa"] == "0.0000"
    assert cuerpo["totales"]["inversion"] == "2500.0000"
    assert cuerpo["totales"]["financiacion"] == "2500.0000"
    # El cuadre se mantiene tras el override.
    assert Decimal(cuerpo["saldo_inicial"]) + Decimal(cuerpo["variacion_neta"]) == Decimal(
        cuerpo["saldo_final"]
    )


# --- Escenario 5: aislamiento multi-empresa ---------------------------------


def test_escenario_5_aislamiento_multi_empresa(cashflow_client):
    cf = cashflow_client
    cuerpo = {
        "desde_fecha": "2026-09-16",
        "hasta_fecha": "2026-09-18",
        "granularidad": "dia",
        "movimientos_manuales": [
            {"tipo": "pago", "importe": "3000.0000", "fecha_prevista": "2026-09-16"}
        ],
    }
    creada_a = cf.post("/api/v1/tesoreria/previsiones", cuerpo, empresa_id=A).json()
    alerta_a = cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()["items"][0]

    # Empresa B no ve las previsiones de A.
    listado_b = cf.get("/api/v1/tesoreria/previsiones", empresa_id=B).json()
    assert listado_b["items"] == []
    assert listado_b["total"] == 0
    assert (
        cf.get(f"/api/v1/tesoreria/previsiones/{creada_a['id']}", empresa_id=B).status_code
        == 404
    )
    # Y tampoco puede consultar ni atender sus alertas.
    assert (
        cf.get(
            "/api/v1/tesoreria/alertas", prevision_id=alerta_a["id"], empresa_id=B
        ).json()["items"]
        == []
    )
    assert (
        cf.post(
            f"/api/v1/tesoreria/alertas/{alerta_a['id']}/atender",
            {"accion": "incluir_ingreso"},
            empresa_id=B,
        ).status_code
        == 404
    )
    # El estado de A no se ha movido.
    assert (
        cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()["total"] == creada_a["n_alertas"]
    )
