"""Aislamiento multi-tenant de las alertas de liquidez (T039, constitucion III).

La alerta de la empresa A es invisible para B: no aparece en su listado, no se
puede filtrar por ella y atenderla o ignorarla desde B devuelve 404.
"""

from __future__ import annotations

A = 10
B = 20
CUERPO = {
    "desde_fecha": "2026-09-16",
    "hasta_fecha": "2026-09-18",
    "granularidad": "dia",
    "movimientos_manuales": [
        {
            "tipo": "pago",
            "importe": "3000.0000",
            "fecha_prevista": "2026-09-16",
            "concepto": "Alquiler",
        }
    ],
}


def _prevision_con_alertas(cf, empresa_id: int = A) -> dict:
    respuesta = cf.post("/api/v1/tesoreria/previsiones", CUERPO, empresa_id=empresa_id)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_alertas_de_A_no_aparecen_en_el_listado_de_B(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_alertas(cf)
    de_a = cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()
    de_b = cf.get("/api/v1/tesoreria/alertas", empresa_id=B).json()
    assert de_a["total"] == creada["n_alertas"]
    assert de_b["total"] == 0
    assert de_b["items"] == []


def test_filtrar_por_prevision_de_A_devuelve_vacio_en_B(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_alertas(cf)
    de_b = cf.get("/api/v1/tesoreria/alertas", prevision_id=creada["id"], empresa_id=B).json()
    assert de_b["total"] == 0
    assert de_b["items"] == []


def test_atender_alerta_de_A_desde_B_devuelve_404(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_alertas(cf)
    alerta = cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()["items"][0]

    atendida = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta['id']}/atender",
        {"accion": "incluir_ingreso"},
        empresa_id=B,
    )
    assert atendida.status_code == 404
    assert atendida.json()["detail"]["code"] == "alerta_no_encontrada"

    ignorada = cf.post(f"/api/v1/tesoreria/alertas/{alerta['id']}/ignorar", empresa_id=B)
    assert ignorada.status_code == 404

    # La alerta de A sigue abierta: el intento desde B no la toco.
    assert (
        cf.get("/api/v1/tesoreria/alertas", estado="abierta", empresa_id=A).json()["total"]
        == creada["n_alertas"]
    )


def test_reprogramar_movimiento_de_A_desde_B_devuelve_404(cashflow_client):
    """El movimiento tambien es multi-tenant: no se puede enlazar el ajeno."""
    cf = cashflow_client
    creada_a = _prevision_con_alertas(cf, A)
    alerta = cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()["items"][0]
    # B tiene su propia prevision y su propia alerta.
    _prevision_con_alertas(cf, B)
    alerta_b = cf.get("/api/v1/tesoreria/alertas", empresa_id=B).json()["items"][0]

    respuesta = cf.post(
        f"/api/v1/tesoreria/alertas/{alerta_b['id']}/atender",
        {
            "accion": "reprogramar_pago",
            "movimiento_id": alerta["movimiento_origen_id"],
            "nueva_fecha": "2026-10-01",
        },
        empresa_id=B,
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "movimiento_no_encontrado"

    # El pago de A sigue en su fecha original.
    detalle_a = cf.get(
        f"/api/v1/tesoreria/previsiones/{creada_a['id']}", empresa_id=A
    ).json()
    pagos = [m for m in detalle_a["movimientos"] if m["tipo"] == "pago"]
    assert [m["fecha_prevista"] for m in pagos] == ["2026-09-16"]


def test_cada_empresa_gestiona_sus_propias_alertas(cashflow_client):
    cf = cashflow_client
    creada_a = _prevision_con_alertas(cf, A)
    creada_b = _prevision_con_alertas(cf, B)
    alertas_a = cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()["items"]
    alertas_b = cf.get("/api/v1/tesoreria/alertas", empresa_id=B).json()["items"]
    assert len(alertas_a) == creada_a["n_alertas"]
    assert len(alertas_b) == creada_b["n_alertas"]
    assert {a["id"] for a in alertas_a}.isdisjoint({a["id"] for a in alertas_b})

    # Atender en A no cierra las de B.
    cf.post(
        f"/api/v1/tesoreria/alertas/{alertas_a[0]['id']}/atender",
        {"accion": "incluir_ingreso"},
        empresa_id=A,
    )
    assert (
        cf.get("/api/v1/tesoreria/alertas", empresa_id=A, estado="abierta").json()["total"]
        == len(alertas_a) - 1
    )
    assert (
        cf.get("/api/v1/tesoreria/alertas", empresa_id=B, estado="abierta").json()["total"]
        == len(alertas_b)
    )


def test_regenerar_prevision_de_A_no_desde_B(cashflow_client):
    cf = cashflow_client
    creada = _prevision_con_alertas(cf)
    assert (
        cf.post(
            f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar", {}, empresa_id=B
        ).status_code
        == 404
    )
    # Las alertas de A siguen donde estaban.
    assert cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()["total"] == creada["n_alertas"]
