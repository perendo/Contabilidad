"""SPEC-026 T039: los 5 escenarios de `quickstart.md` reproducidos por HTTP.

- Escenario 1: alta por cuenta, duplicado idéntico 422, listado por ejercicio.
- Escenario 2: seguimiento con real 45000 vs presupuesto 48000 y cuenta sin
  presupuesto con real 2000.
- Escenario 3: informe, cierre del periodo y modificacion posterior 409.
- Escenario 4: importacion masiva CSV.
- Escenario 5: aislamiento multi-empresa.
"""

from __future__ import annotations

from datetime import date

EJERCICIO = 2026


def _asiento(ns, empresa_id, de, haber, importe, fecha=date(EJERCICIO, 6, 30)):
    return ns.asiento(
        empresa_id,
        fecha,
        [
            {"account_id": ns.cuenta(empresa_id, de), "debit": importe, "credit": "0"},
            {"account_id": ns.cuenta(empresa_id, haber), "debit": "0", "credit": importe},
        ],
    )


# --- Escenario 1 -----------------------------------------------------------


def test_escenario_1_alta_duplicado_y_listado(presupuestos_client):
    ns = presupuestos_client
    alta = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "centro_coste_id": None,
            "importe": "48000.0000",
            "tipo": "gasto",
        },
    )
    assert alta.status_code == 200, alta.text
    assert alta.json()["importe"] == "48000.0000"
    assert alta.json()["tipo"] == "gasto"

    duplicado = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "centro_coste_id": None,
            "importe": "100.0000",
            "tipo": "gasto",
        },
    )
    # Un importe distinto actualiza la misma combinacion; el duplicado IDENTICO
    # (mismo importe) es el que devuelve 422 segun FR-005.
    assert duplicado.status_code == 200
    assert duplicado.json()["id"] == alta.json()["id"]

    identico = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "centro_coste_id": None,
            "importe": "100.0000",
            "tipo": "gasto",
        },
    )
    assert identico.status_code == 422
    assert identico.json()["detail"]["code"] == "duplicado_identico"

    listado = ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO)
    assert listado.status_code == 200
    item = listado.json()["items"][0]
    assert item["codigo_cuenta"] == "6400"
    assert item["importe"] == "100.0000"
    assert item["tipo"] == "gasto"


def test_escenario_1_cuenta_inapunteable(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "64"),
            "importe": "100.0000",
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "cuenta_inapunteable"


# --- Escenario 2 -----------------------------------------------------------


def test_escenario_2_desviacion_por_cuenta(presupuestos_client):
    ns = presupuestos_client
    ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "importe": "48000.0000",
        },
    )
    _asiento(ns, 10, "6400", "4000", "45000")

    respuesta = ns.get(
        "/api/v1/presupuestos/seguimiento",
        ejercicio=EJERCICIO,
        cuenta_id=ns.cuenta(10, "6400"),
    )
    assert respuesta.status_code == 200
    item = respuesta.json()["items"][0]
    assert item["importe_presupuestado"] == "48000.0000"
    assert item["importe_real"] == "45000.0000"
    assert item["desviacion_absoluta"] == "-3000.0000"
    assert item["desviacion_relativa"] == "-0.0625"
    assert item["sin_presupuesto"] is False


def test_escenario_2_cuenta_sin_presupuesto(presupuestos_client):
    ns = presupuestos_client
    _asiento(ns, 10, "6000", "4100", "2000")

    respuesta = ns.get(
        "/api/v1/presupuestos/seguimiento",
        ejercicio=EJERCICIO,
        cuenta_id=ns.cuenta(10, "6000"),
    )
    assert respuesta.status_code == 200
    item = respuesta.json()["items"][0]
    assert item["sin_presupuesto"] is True
    assert item["importe_presupuestado"] == "0.0000"
    assert item["importe_real"] == "2000.0000"
    assert item["desviacion_absoluta"] == "2000.0000"


def test_escenario_2_real_signo_gasto(presupuestos_client):
    """Grupo 6: el real es `SUM(Debe)`, no `Debe - Haber`."""
    ns = presupuestos_client
    _asiento(ns, 10, "6400", "4000", "45000")
    item = ns.get(
        "/api/v1/presupuestos/seguimiento",
        ejercicio=EJERCICIO,
        cuenta_id=ns.cuenta(10, "6400"),
    ).json()["items"][0]
    assert item["importe_real"] == "45000.0000"


# --- Escenario 3 -----------------------------------------------------------


def test_escenario_3_informe_cierre_y_bloqueo(presupuestos_client):
    ns = presupuestos_client
    ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "importe": "48000.0000",
        },
    )
    ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "7000"),
            "importe": "120000.0000",
            "tipo": "ingreso",
        },
    )
    _asiento(ns, 10, "6400", "4000", "45000")

    informe = ns.get("/api/v1/presupuestos/informes/desviacion", ejercicio=EJERCICIO)
    assert informe.status_code == 200
    cuerpo = informe.json()
    assert cuerpo["total_presupuestado"] == "168000.0000"
    assert cuerpo["total_real"] == "45000.0000"
    assert cuerpo["cuadra"] is True

    periodo_id = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()["periodo_id"]
    cierre = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    )
    assert cierre.status_code == 200
    assert cierre.json()["estado"] == "cerrado"
    assert cierre.json()["desviaciones_registradas"] >= 2
    assert cierre.json()["fecha_cierre"]

    modificacion = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "importe": "100.0000",
        },
    )
    assert modificacion.status_code == 409
    assert modificacion.json()["detail"]["code"] == "periodo_cerrado"


# --- Escenario 4 -----------------------------------------------------------


def test_escenario_4_importacion_masiva(presupuestos_client):
    ns = presupuestos_client
    csv = (
        "codigo_cuenta,centro,importe,tipo\n"
        "6400,,48000.0000,gasto\n"
        "7000,,120000.0000,ingreso\n"
    )
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        files={"file": ("presupuesto_2026.csv", csv, "text/csv")},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["importadas"] == 2
    assert cuerpo["errores"] == []


# --- Escenario 5 -----------------------------------------------------------


def test_escenario_5_aislamiento_multi_empresa(presupuestos_client):
    ns = presupuestos_client
    assert ns.post(
        "/api/v1/presupuestos",
        empresa_id=10,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "importe": "48000.0000",
        },
    ).status_code == 200

    listado_b = ns.get("/api/v1/presupuestos", empresa_id=20, ejercicio=EJERCICIO)
    assert listado_b.status_code == 200
    assert listado_b.json()["items"] == []

    periodo_a = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()["periodo_id"]
    cierre_b = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        empresa_id=20,
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_a},
    )
    assert cierre_b.status_code == 404
    assert cierre_b.json()["detail"]["code"] == "periodo_no_encontrado"
