"""SPEC-026 US1 · T018: aislamiento multi-tenant del presupuesto (constitucion III).

La empresa B no ve los presupuestos de la A, no puede filtrar por sus cuentas
ni guardar con una cuenta o un centro de la A (422), y su ejercicio es
independiente.
"""

from __future__ import annotations

EJERCICIO = 2026


def _alta(ns, empresa_id: int, codigo: str, importe: str = "48000.0000"):
    return ns.post(
        "/api/v1/presupuestos",
        empresa_id=empresa_id,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(empresa_id, codigo),
            "importe": importe,
        },
    )


def test_listado_de_B_no_muestra_las_lineas_de_A(presupuestos_client):
    ns = presupuestos_client
    assert _alta(ns, 10, "6400").status_code == 200

    de_a = ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO).json()
    assert de_a["total"] == 1
    assert de_a["items"][0]["codigo_cuenta"] == "6400"

    de_b = ns.get("/api/v1/presupuestos", empresa_id=20, ejercicio=EJERCICIO).json()
    assert de_b["total"] == 0
    assert de_b["items"] == []


def test_cuenta_de_A_rechazada_desde_B(presupuestos_client):
    ns = presupuestos_client
    cuenta_de_a = ns.cuenta(10, "6400")
    respuesta = ns.post(
        "/api/v1/presupuestos",
        empresa_id=20,
        json={"ejercicio": EJERCICIO, "cuenta_id": cuenta_de_a, "importe": "1.0000"},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "cuenta_no_encontrada"
    assert ns.get("/api/v1/presupuestos", empresa_id=20, ejercicio=EJERCICIO).json()[
        "total"
    ] == 0


def test_centro_de_A_rechazado_desde_B(presupuestos_client):
    ns = presupuestos_client
    centro_de_a = ns.centros(10)["CC-01"]
    respuesta = ns.post(
        "/api/v1/presupuestos",
        empresa_id=20,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(20, "6400"),
            "centro_coste_id": centro_de_a,
            "importe": "1.0000",
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "centro_no_encontrado"


def test_cada_empresa_mantiene_su_propia_combinacion(presupuestos_client):
    ns = presupuestos_client
    assert _alta(ns, 10, "6400", "48000.0000").status_code == 200
    assert _alta(ns, 20, "6400", "33000.0000").status_code == 200

    importes_a = {
        i["codigo_cuenta"]: i["importe"]
        for i in ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO).json()["items"]
    }
    importes_b = {
        i["codigo_cuenta"]: i["importe"]
        for i in ns.get("/api/v1/presupuestos", empresa_id=20, ejercicio=EJERCICIO).json()[
            "items"
        ]
    }
    assert importes_a == {"6400": "48000.0000"}
    assert importes_b == {"6400": "33000.0000"}


def test_importacion_de_B_no_toca_las_lineas_de_A(presupuestos_client):
    ns = presupuestos_client
    assert _alta(ns, 10, "6400", "48000.0000").status_code == 200
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        empresa_id=20,
        json={
            "ejercicio": EJERCICIO,
            "lineas": [
                {"codigo_cuenta": "9999", "importe": "1.0000"},
            ],
        },
    )
    assert respuesta.status_code == 422
    assert "cuenta_no_encontrada" in respuesta.json()["detail"]["errores"][0]["motivo"]
    assert ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO).json()["total"] == 1


def test_usuario_sin_acceso_a_la_empresa_recibe_403(presupuestos_client):
    """El usuario 3 (READ_ONLY) esta vinculado a 10 y 20; el resto no existe."""
    ns = presupuestos_client
    respuesta = ns.get("/api/v1/presupuestos", empresa_id=99)
    assert respuesta.status_code == 403
    assert "empresa" in str(respuesta.json()["detail"]).lower()
