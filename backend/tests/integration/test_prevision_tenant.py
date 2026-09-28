"""Aislamiento multi-tenant de la prevision de tesoreria (T021, constitucion III).

Empresa A genera la prevision; empresa B no la ve en el listado ni en el
detalle, y el intento de regenerarla devuelve 404 (no 403: no se revela ni la
existencia del recurso). Tambien se cubre el matrice RBAC del modulo
`treasury`: READ_ONLY no genera, ACCOUNTANT si.
"""

from __future__ import annotations

import pytest

EJERCICIO = 2026
A = 10
B = 20
CUERPO = {
    "desde_fecha": "2026-09-16",
    "hasta_fecha": "2026-10-31",
    "granularidad": "dia",
}


def _previsiones_de_A(cashflow_client) -> dict:
    return cashflow_client.post(
        "/api/v1/tesoreria/previsiones", CUERPO, empresa_id=A
    ).json()


def test_listado_de_B_no_muestra_previsiones_de_A(cashflow_client):
    creada = _previsiones_de_A(cashflow_client)
    assert creada["id"]

    de_a = cashflow_client.get("/api/v1/tesoreria/previsiones", empresa_id=A).json()
    de_b = cashflow_client.get("/api/v1/tesoreria/previsiones", empresa_id=B).json()
    assert de_a["total"] == 1
    assert de_b["total"] == 0
    assert de_b["items"] == []


def test_detalle_de_prevision_de_A_devuelve_404_en_B(cashflow_client):
    creada = _previsiones_de_A(cashflow_client)
    respuesta = cashflow_client.get(
        f"/api/v1/tesoreria/previsiones/{creada['id']}", empresa_id=B
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "prevision_no_encontrada"


def test_regenerar_desde_B_devuelve_404(cashflow_client):
    creada = _previsiones_de_A(cashflow_client)
    respuesta = cashflow_client.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/regenerar", {}, empresa_id=B
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "prevision_no_encontrada"

    # Y la prevision de A sigue intacta.
    detalle = cashflow_client.get(
        f"/api/v1/tesoreria/previsiones/{creada['id']}", empresa_id=A
    ).json()
    assert detalle["numero_prevision"] == creada["numero_prevision"]


def test_alta_de_movimiento_en_prevision_de_A_desde_B_devuelve_404(cashflow_client):
    creada = _previsiones_de_A(cashflow_client)
    respuesta = cashflow_client.post(
        f"/api/v1/tesoreria/previsiones/{creada['id']}/movimientos",
        {"tipo": "pago", "importe": "10.0000", "fecha_prevista": "2026-10-01"},
        empresa_id=B,
    )
    assert respuesta.status_code == 404


def test_cada_empresa_mantiene_su_correlatividad(cashflow_client):
    cf = cashflow_client
    primera_a = cf.post("/api/v1/tesoreria/previsiones", CUERPO, empresa_id=A).json()
    primera_b = cf.post("/api/v1/tesoreria/previsiones", CUERPO, empresa_id=B).json()
    segunda_a = cf.post("/api/v1/tesoreria/previsiones", CUERPO, empresa_id=A).json()
    assert primera_a["numero_prevision"] == 1
    assert primera_b["numero_prevision"] == 1
    assert segunda_a["numero_prevision"] == 2


def test_vencimientos_de_otra_empresa_no_entran_en_la_proyeccion(cashflow_client):
    cf = cashflow_client
    cf.vencimientos(
        empresa_id=B,
        especificaciones=[{"fecha_vencimiento": "2026-10-05", "importe": "7000.0000"}],
    )
    creada = cf.post("/api/v1/tesoreria/previsiones", CUERPO, empresa_id=A).json()
    assert creada["n_movimientos"] == 0
    assert creada["saldo_final"] == creada["saldo_inicial"]


def test_saldo_inicial_aislado_por_empresa(cashflow_client):
    """El saldo de tesoreria de A no se filtra al saldo inicial de B."""
    cf = cashflow_client
    cf.plantar(empresa_id=A, code="1000", parent="100", name="Capital social")
    cf.asiento(
        empresa_id=A,
        fecha="2026-01-05",
        lineas=[
            {"cuenta": "5720", "debe": "9000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "9000.0000"},
        ],
        tipo="OPENING",
    )
    de_a = cf.post("/api/v1/tesoreria/previsiones", CUERPO, empresa_id=A).json()
    de_b = cf.post("/api/v1/tesoreria/previsiones", CUERPO, empresa_id=B).json()
    assert de_a["saldo_inicial"] == "9000.0000"
    assert de_a["origen_saldo_inicial"] == "diario"
    assert de_b["saldo_inicial"] == "0.0000"


# --- Constitucion III: contexto de empresa obligatorio ----------------------


def test_sin_cabecera_de_empresa_devuelve_403(cashflow_client):
    """La empresa activa se deriva de la sesion: sin cabecera no hay contexto."""
    solo_token = {"Authorization": f"Bearer {cashflow_client.tokens['admin']}"}
    respuesta = cashflow_client.client.get(
        "/api/v1/tesoreria/previsiones", headers=solo_token
    )
    assert respuesta.status_code == 403


def test_sin_token_devuelve_401(cashflow_client):
    respuesta = cashflow_client.client.get(
        "/api/v1/tesoreria/previsiones", headers={"X-Empresa-Activa": str(A)}
    )
    assert respuesta.status_code == 401


def test_empresa_no_vinculada_al_usuario_devuelve_403(cashflow_client):
    respuesta = cashflow_client.get(
        "/api/v1/tesoreria/previsiones", empresa_id=999
    )
    assert respuesta.status_code == 403


# --- RBAC del modulo treasury (SPEC-015) ------------------------------------


def test_read_only_no_puede_generar(cashflow_client):
    respuesta = cashflow_client.post(
        "/api/v1/tesoreria/previsiones", CUERPO, token_key="readonly"
    )
    assert respuesta.status_code == 403
    assert cashflow_client.get("/api/v1/tesoreria/previsiones").json()["total"] == 0


def test_read_only_si_puede_consultar(cashflow_client):
    _previsiones_de_A(cashflow_client)
    respuesta = cashflow_client.get(
        "/api/v1/tesoreria/previsiones", token_key="readonly"
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 1


def test_accountant_puede_generar_pero_no_formular_efe(cashflow_client):
    creada = cashflow_client.post(
        "/api/v1/tesoreria/previsiones", CUERPO, token_key="accountant"
    )
    assert creada.status_code == 201
    formular = cashflow_client.post(
        "/api/v1/tesoreria/efe/formular",
        {"ejercicio": EJERCICIO},
        token_key="accountant",
    )
    assert formular.status_code == 403


@pytest.mark.parametrize("ruta", ["/api/v1/tesoreria/previsiones", "/api/v1/tesoreria/alertas"])
def test_rutas_de_lectura_no_requieren_cuerpo(cashflow_client, ruta):
    respuesta = cashflow_client.get(ruta)
    assert respuesta.status_code == 200
