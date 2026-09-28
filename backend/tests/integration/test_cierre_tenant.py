"""SPEC-026 US3 · T036: aislamiento multi-tenant del cierre y del snapshot.

La empresa B no ve el snapshot de A, no puede cerrar su periodo (404) y su
propio cierre no le revela nada de A (constitucion III).
"""

from __future__ import annotations

import uuid

EJERCICIO = 2026


def _crear_periodo(ns, empresa_id: int) -> str:
    respuesta = ns.post(
        "/api/v1/presupuestos/periodos",
        empresa_id=empresa_id,
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["periodo_id"]


def test_cierre_de_A_no_es_visible_desde_B(presupuestos_client):
    ns = presupuestos_client
    periodo_a = _crear_periodo(ns, 10)
    assert ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_a},
    ).status_code == 200

    listado_b = ns.get("/api/v1/presupuestos/periodos", empresa_id=20, ejercicio=EJERCICIO)
    assert listado_b.json()["total"] == 0

    snapshot_b = ns.get(
        "/api/v1/presupuestos/seguimiento/snapshot",
        empresa_id=20,
        periodo_id=periodo_a,
    )
    assert snapshot_b.status_code == 404
    assert snapshot_b.json()["detail"]["code"] == "periodo_no_encontrado"


def test_cerrar_el_periodo_de_A_desde_B_es_404(presupuestos_client):
    ns = presupuestos_client
    periodo_a = _crear_periodo(ns, 10)
    respuesta = ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        empresa_id=20,
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_a},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "periodo_no_encontrado"

    estado_a = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()
    assert estado_a["estado"] == "abierto"


def test_el_cierre_de_B_no_bloquea_el_presupuesto_de_A(presupuestos_client):
    ns = presupuestos_client
    periodo_b = _crear_periodo(ns, 20)
    assert ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        empresa_id=20,
        json={"ejercicio": EJERCICIO, "periodo_id": periodo_b},
    ).status_code == 200

    alta_a = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "importe": "48000.0000",
        },
    )
    assert alta_a.status_code == 200


def test_snapshots_independientes_por_empresa(presupuestos_client):
    ns = presupuestos_client
    for empresa_id, importe in ((10, "48000.0000"), (20, "30000.0000")):
        _crear_periodo(ns, empresa_id)
        ns.post(
            "/api/v1/presupuestos",
            empresa_id=empresa_id,
            json={
                "ejercicio": EJERCICIO,
                "cuenta_id": ns.cuenta(empresa_id, "6400"),
                "importe": importe,
            },
        )
        periodo = ns.get(
            "/api/v1/presupuestos/seguimiento/periodo",
            empresa_id=empresa_id,
            ejercicio=EJERCICIO,
        ).json()["periodo_id"]
        assert ns.post(
            "/api/v1/presupuestos/informes/cerrar",
            empresa_id=empresa_id,
            json={"ejercicio": EJERCICIO, "periodo_id": periodo},
        ).status_code == 200

    for empresa_id, importe in ((10, "48000.0000"), (20, "30000.0000")):
        periodos = ns.get(
            "/api/v1/presupuestos/periodos", empresa_id=empresa_id, ejercicio=EJERCICIO
        ).json()
        assert periodos["total"] == 1
        snapshot = ns.get(
            "/api/v1/presupuestos/seguimiento/snapshot",
            empresa_id=empresa_id,
            periodo_id=periodos["items"][0]["periodo_id"],
        ).json()
        fila = next(i for i in snapshot["items"] if i["codigo_cuenta"] == "6400")
        assert fila["importe_presupuestado"] == importe
        assert fila["importe_presupuestado"] != snapshot["total"] * "0"
        assert fila["importe_real"] == "0.0000"


def test_periodo_inexistente_es_404_tambien_para_B(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.get(
        "/api/v1/presupuestos/seguimiento/snapshot",
        empresa_id=20,
        periodo_id=str(uuid.uuid4()),
    )
    assert respuesta.status_code == 404
