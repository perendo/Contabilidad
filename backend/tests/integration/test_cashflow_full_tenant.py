"""Endurecimiento multi-tenant del modulo de tesoreria (T041, constitucion III).

Escenario completo cruzado: la prevision de A, el EFE de A y una alerta de A
atendida desde B. Todo acceso cruzado devuelve 404/403 y el estado de A no
cambia en ningun caso.
"""

from __future__ import annotations

A = 10
B = 20
CUERPO_PREVISION = {
    "desde_fecha": "2026-09-16",
    "hasta_fecha": "2026-09-18",
    "granularidad": "dia",
    "movimientos_manuales": [
        {
            "tipo": "pago",
            "importe": "8000.0000",
            "fecha_prevista": "2026-09-16",
            "concepto": "Alquiler",
        }
    ],
}


def _escapenario(cf, empresa_id: int) -> dict:
    """Ejercicio completo de la empresa: prevision con deficit + EFE con datos."""
    cf.plantar(empresa_id=empresa_id, code="1000", parent="100", name="Capital")
    cf.asiento(
        empresa_id=empresa_id,
        fecha="2026-01-02",
        lineas=[
            {"cuenta": "5720", "debe": "5000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "5000.0000"},
        ],
        concepto="Apertura",
        tipo="OPENING",
    )
    cf.asiento(
        empresa_id=empresa_id,
        fecha="2026-04-01",
        lineas=[
            {"cuenta": "5720", "debe": "2000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "2000.0000"},
        ],
        concepto="Cobro de venta",
    )
    prevision = cf.post(
        "/api/v1/tesoreria/previsiones", CUERPO_PREVISION, empresa_id=empresa_id
    ).json()
    return prevision


def test_ciclo_completo_cruzado_no_filtra_nada(cashflow_client):
    cf = cashflow_client
    prevision_a = _escapenario(cf, A)
    prevision_b = _escapenario(cf, B)
    alerta_a = cf.get("/api/v1/tesoreria/alertas", empresa_id=A).json()["items"][0]
    alerta_b = cf.get("/api/v1/tesoreria/alertas", empresa_id=B).json()["items"][0]
    assert prevision_a["id"] != prevision_b["id"]
    assert alerta_a["id"] != alerta_b["id"]

    # B no ve la prevision de A ni sus movimientos.
    assert cf.get("/api/v1/tesoreria/previsiones", empresa_id=B).json()["total"] == 1
    assert (
        cf.get(f"/api/v1/tesoreria/previsiones/{prevision_a['id']}", empresa_id=B).status_code
        == 404
    )
    # B no ve el EFE de A (tiene el suyo propio, con sus datos).
    efe_a = cf.get("/api/v1/tesoreria/efe", ejercicio=2026, empresa_id=A).json()
    efe_b = cf.get("/api/v1/tesoreria/efe", ejercicio=2026, empresa_id=B).json()
    assert efe_a["saldo_final"] == efe_b["saldo_final"] == "7000.0000"
    assert efe_a["informe_id"] is None and efe_b["informe_id"] is None

    # Formular el EFE en A no lo hace visible en B.
    formulado_a = cf.post(
        "/api/v1/tesoreria/efe/formular", {"ejercicio": 2026}, empresa_id=A
    ).json()
    assert (
        cf.get("/api/v1/tesoreria/efe", ejercicio=2026, empresa_id=A).json()["informe_id"]
        == formulado_a["informe_id"]
    )
    assert cf.get("/api/v1/tesoreria/efe", ejercicio=2026, empresa_id=B).json()["formulado"] is False

    # Atender la alerta de A desde B es un 404 y no la cierra.
    assert (
        cf.post(
            f"/api/v1/tesoreria/alertas/{alerta_a['id']}/atender",
            {"accion": "incluir_ingreso"},
            empresa_id=B,
        ).status_code
        == 404
    )
    assert (
        cf.post(f"/api/v1/tesoreria/alertas/{alerta_a['id']}/ignorar", empresa_id=B).status_code
        == 404
    )
    assert (
        cf.get("/api/v1/tesoreria/alertas", estado="abierta", empresa_id=A).json()["total"]
        == prevision_a["n_alertas"]
    )
    # Y la de B sigue como estaba.
    assert (
        cf.get("/api/v1/tesoreria/alertas", estado="abierta", empresa_id=B).json()["total"]
        == prevision_b["n_alertas"]
    )


def test_regenerar_desde_B_no_afecta_a_A(cashflow_client):
    cf = cashflow_client
    prevision_a = _escapenario(cf, A)
    assert (
        cf.post(
            f"/api/v1/tesoreria/previsiones/{prevision_a['id']}/regenerar", {}, empresa_id=B
        ).status_code
        == 404
    )
    detalle = cf.get(f"/api/v1/tesoreria/previsiones/{prevision_a['id']}", empresa_id=A).json()
    assert detalle["numero_prevision"] == prevision_a["numero_prevision"]
    assert detalle["saldo_final"] == prevision_a["saldo_final"]
    assert len(detalle["alertas"]) == prevision_a["n_alertas"]


def test_una_empresa_solo_contesta_por_su_contexto(cashflow_client):
    """Mismo usuario, dos empresas: cada peticion ve exactamente su empresa."""
    cf = cashflow_client
    prevision_a = _escapenario(cf, A)
    prevision_b = _escapenario(cf, B)
    assert prevision_a["saldo_inicial"] == prevision_b["saldo_inicial"]
    assert prevision_a["numero_prevision"] == prevision_b["numero_prevision"] == 1
    detalle_a = cf.get(f"/api/v1/tesoreria/previsiones/{prevision_a['id']}", empresa_id=A).json()
    detalle_b = cf.get(f"/api/v1/tesoreria/previsiones/{prevision_b['id']}", empresa_id=B).json()
    assert detalle_a["id"] != detalle_b["id"]
    # Y el mismo id en la otra empresa no resuelve.
    assert (
        cf.get(f"/api/v1/tesoreria/previsiones/{prevision_a['id']}", empresa_id=B).status_code
        == 404
    )


def test_empresa_no_membership_devuelve_403(cashflow_client):
    cf = cashflow_client
    _escapenario(cf, A)
    for ruta in (
        "/api/v1/tesoreria/previsiones",
        "/api/v1/tesoreria/alertas",
    ):
        assert cf.get(ruta, empresa_id=999).status_code == 403
    assert (
        cf.post(
            "/api/v1/tesoreria/previsiones", CUERPO_PREVISION, empresa_id=999
        ).status_code
        == 403
    )


def test_cabecera_de_empresa_invalida_devuelve_403(cashflow_client):
    cf = cashflow_client
    for valor in ("0", "-5", "abc"):
        respuesta = cf.client.get(
            "/api/v1/tesoreria/previsiones",
            headers={"Authorization": f"Bearer {cf.tokens['admin']}", "X-Empresa-Activa": valor},
        )
        assert respuesta.status_code == 403, valor
