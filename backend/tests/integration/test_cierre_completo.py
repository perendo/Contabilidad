"""SPEC-026 US3 · T035: cierre completo por HTTP (quickstart Escenario 3).

Presupuesto + asientos reales -> informe -> cierre del periodo -> snapshot
consultable e inmutable; despues, cualquier intento de modificar el presupuesto
devuelve 409.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

EJERCICIO = 2026


def _preparar(ns, empresa_id: int = 10) -> None:
    ns.post(
        "/api/v1/presupuestos",
        empresa_id=empresa_id,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(empresa_id, "6400"),
            "importe": "48000.0000",
        },
    )
    ns.asiento(
        empresa_id,
        date(EJERCICIO, 6, 30),
        [
            {
                "account_id": ns.cuenta(empresa_id, "6400"),
                "debit": "45000",
                "credit": "0",
            },
            {
                "account_id": ns.cuenta(empresa_id, "4000"),
                "debit": "0",
                "credit": "45000",
            },
        ],
    )


def test_quickstart_escenario_3(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns)

    periodo = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()
    assert periodo["estado"] == "abierto"
    periodo_id = periodo["periodo_id"]

    informe = ns.get("/api/v1/presupuestos/informes/desviacion", ejercicio=EJERCICIO).json()
    assert informe["total_presupuestado"] != "0.0000"
    assert informe["total_real"] != "0.0000"
    assert informe["cuadra"] is True
    assert informe["centros"]

    cierre = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    )
    assert cierre.status_code == 200, cierre.text
    cuerpo = cierre.json()
    assert cuerpo["estado"] == "cerrado"
    assert cuerpo["desviaciones_registradas"] > 0
    assert cuerpo["fecha_cierre"] is not None
    assert cuerpo["cerrado_por"] is not None

    estado = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()
    assert estado["estado"] == "cerrado"
    assert estado["fecha_cierre"] is not None

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


def test_snapshot_consultable_tras_el_cierre(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns)
    periodo_id = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()["periodo_id"]
    ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    )

    snapshot = ns.get(
        "/api/v1/presupuestos/seguimiento/snapshot", periodo_id=periodo_id
    ).json()
    assert snapshot["periodo_id"] == periodo_id
    fila = next(i for i in snapshot["items"] if i["codigo_cuenta"] == "6400")
    assert fila["importe_presupuestado"] == "48000.0000"
    assert fila["importe_real"] == "45000.0000"
    assert fila["desviacion_absoluta"] == "-3000.0000"
    assert fila["desviacion_relativa"] == "-0.0625"


def test_informe_sirve_desde_el_snapshot_tras_cerrar(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns)
    periodo_id = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()["periodo_id"]
    calculado = ns.get(
        "/api/v1/presupuestos/informes/desviacion", ejercicio=EJERCICIO
    ).json()
    ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    )
    desde_snapshot = ns.get(
        "/api/v1/presupuestos/informes/desviacion",
        ejercicio=EJERCICIO,
        periodo_id=periodo_id,
    ).json()
    assert desde_snapshot["origen"] == "snapshot"
    assert Decimal(desde_snapshot["total_desviacion"]) == Decimal(
        calculado["total_desviacion"]
    )


def test_doble_cierre_es_409(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns)
    periodo_id = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()["periodo_id"]
    primero = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    )
    assert primero.status_code == 200
    segundo = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    )
    assert segundo.status_code == 409
    assert segundo.json()["detail"]["code"] == "periodo_ya_cerrado"


def test_cerrar_un_periodo_inexistente_es_404(presupuestos_client):
    import uuid

    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": str(uuid.uuid4())},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "periodo_no_encontrado"


def test_cerrar_sin_datos_devuelve_cero(presupuestos_client):
    ns = presupuestos_client
    periodo = ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
        },
    )
    cierre = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={
            "ejercicio": EJERCICIO,
            "periodo_id": periodo.json()["periodo_id"],
        },
    )
    assert cierre.status_code == 200
    assert cierre.json()["desviaciones_registradas"] == 0


def test_rbac_read_only_no_puede_cerrar(presupuestos_client):
    ns = presupuestos_client
    periodo = ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
        },
    )
    respuesta = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        token_key="readonly",
        json={
            "ejercicio": EJERCICIO,
            "periodo_id": periodo.json()["periodo_id"],
        },
    )
    assert respuesta.status_code == 403
    assert (
        ns.get(
            "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
        ).json()["estado"]
        == "abierto"
    )
