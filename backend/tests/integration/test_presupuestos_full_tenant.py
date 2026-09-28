"""SPEC-026 T038: hardening multi-tenant extremo a extremo (constitucion III).

Escenario completo cross-empresa: la empresa A define presupuesto, consulta el
seguimiento, cierra el periodo y consulta su snapshot; desde la empresa B cada
operacion devuelve 404/403 y los datos de A nunca aparecen. Incluye el intento
de escribir con el `empresa_id` de A en el body (que debe ignorarse).
"""

from __future__ import annotations

import uuid
from datetime import date

EJERCICIO = 2026
A = 10
B = 20


def _alta(ns, empresa_id: int, codigo: str = "6400", importe: str = "48000.0000"):
    return ns.post(
        "/api/v1/presupuestos",
        empresa_id=empresa_id,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(empresa_id, codigo),
            "importe": importe,
        },
    )


def _gasto(ns, empresa_id: int, importe: str = "45000"):
    return ns.asiento(
        empresa_id,
        date(EJERCICIO, 6, 30),
        [
            {
                "account_id": ns.cuenta(empresa_id, "6400"),
                "debit": importe,
                "credit": "0",
            },
            {
                "account_id": ns.cuenta(empresa_id, "4000"),
                "debit": "0",
                "credit": importe,
            },
        ],
    )


def test_recorrido_completo_en_A(presupuestos_client):
    ns = presupuestos_client
    assert _alta(ns, A).status_code == 200
    _gasto(ns, A)

    seguimiento = ns.get("/api/v1/presupuestos/seguimiento", ejercicio=EJERCICIO).json()
    assert seguimiento["total"] == 1
    assert seguimiento["items"][0]["desviacion_absoluta"] == "-3000.0000"

    periodo_id = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()["periodo_id"]
    cierre = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_id},
    )
    assert cierre.status_code == 200

    snapshot = ns.get(
        "/api/v1/presupuestos/seguimiento/snapshot", periodo_id=periodo_id
    ).json()
    assert snapshot["total"] == 1


def test_desde_B_todo_devuelve_404_o_vacio(presupuestos_client):
    ns = presupuestos_client
    assert _alta(ns, A).status_code == 200
    _gasto(ns, A)
    periodo_a = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()["periodo_id"]
    ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_a},
    )

    assert ns.get("/api/v1/presupuestos", empresa_id=B, ejercicio=EJERCICIO).json()["total"] == 0
    assert (
        ns.get(
            "/api/v1/presupuestos/seguimiento", empresa_id=B, ejercicio=EJERCICIO
        ).json()["total"]
        == 0
    )
    assert (
        ns.get(
            "/api/v1/presupuestos/informes/desviacion", empresa_id=B, ejercicio=EJERCICIO
        ).json()["total"]
        == 0
    )
    assert ns.get("/api/v1/presupuestos/periodos", empresa_id=B).json()["total"] == 0
    assert ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", empresa_id=B, ejercicio=EJERCICIO
    ).json()["estado"] == "sin_periodo"
    assert (
        ns.get(
            "/api/v1/presupuestos/seguimiento/snapshot",
            empresa_id=B,
            periodo_id=periodo_a,
        ).status_code
        == 404
    )
    assert (
        ns.post(
            "/api/v1/presupuestos/informes/cerrar",
            empresa_id=B,
            json={"ejercicio": EJERCICIO, "periodo_id": periodo_a},
        ).status_code
        == 404
    )


def test_el_body_intenta_inyectar_la_empresa_de_A(presupuestos_client):
    """Constitucion III: `empresa_id` en el body se ignora; manda la sesion."""
    ns = presupuestos_client
    _alta(ns, A, importe="48000.0000")

    respuesta = ns.post(
        "/api/v1/presupuestos",
        empresa_id=B,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(A, "6400"),
            "importe": "999.0000",
            "empresa_id": A,
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "cuenta_no_encontrada"

    assert ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO).json()["items"][0][
        "importe"
    ] == "48000.0000"
    assert ns.get("/api/v1/presupuestos", empresa_id=B, ejercicio=EJERCICIO).json()[
        "total"
    ] == 0


def test_importacion_de_B_con_fichero_de_A_no_afecta_a_A(presupuestos_client):
    ns = presupuestos_client
    _alta(ns, A, importe="48000.0000")
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        empresa_id=B,
        files={
            "file": (
                "presupuesto_2026.csv",
                "6400;CC-01;7777.0000;gasto\n",
                "text/csv",
            )
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["importadas"] == 1

    de_a = ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO).json()
    assert de_a["total"] == 1
    assert de_a["items"][0]["importe"] == "48000.0000"
    assert de_a["items"][0]["centro_coste_id"] is None


def test_sin_relacion_con_la_empresa_es_403(presupuestos_client):
    ns = presupuestos_client
    for empresa_id in (30, 999):
        assert ns.get("/api/v1/presupuestos", empresa_id=empresa_id).status_code == 403
    assert ns.get("/api/v1/presupuestos", empresa_id=0).status_code == 403


def test_periodo_aleatorio_de_otra_empresa_es_404(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        empresa_id=B,
        json={"ejercicio": EJERCICIO, "periodo_id": str(uuid.uuid4())},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "periodo_no_encontrado"
