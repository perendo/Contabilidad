"""Escenarios del quickstart de cuentas anuales (SPEC-010 T041)."""

from __future__ import annotations


def _get(fac, empresa_id, recurso, **params):
    return fac.get(empresa_id, f"/api/v1/cuentas-anuales/2026/{recurso}", **params)


def test_scenario_1_balance_provisional(cuentas_client) -> None:
    fac = cuentas_client
    data = _get(fac, 10, "balance").json()
    assert data["cuadre"] is True
    assert _get(fac, 20, "balance").json()["total_activo"] != data["total_activo"]


def test_scenario_2_pyg_coincide_cierre(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    data = _get(fac, 10, "pyg").json()
    assert data["coincide_cierre"] is True


def test_scenario_3_formular(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    r = fac.post("/api/v1/cuentas-anuales/2026/formular", json={"observaciones": "A"})
    assert r.status_code == 201
    assert r.json()["numero_formulacion"] == 1
    items = _get(fac, 10, "formulaciones").json()["items"]
    assert len(items) == 1


def test_scenario_4_anular_reformular(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    fac.post("/api/v1/cuentas-anuales/2026/formular", json={})
    fac.post(
        "/api/v1/cuentas-anuales/2026/anular-formulacion",
        json={"motivo": "correccion"},
    )
    segunda = fac.post("/api/v1/cuentas-anuales/2026/formular", json={})
    assert segunda.json()["numero_formulacion"] == 2
    assert len(_get(fac, 10, "formulaciones").json()["items"]) == 2


def test_scenario_5_efe_cuadre(cuentas_client) -> None:
    fac = cuentas_client
    data = _get(fac, 10, "efe").json()
    assert data["cuadre"] is True
    assert data["saldo_final_tesoreria"] == data["variacion_neta"]


def test_scenario_6_aislamiento(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    fac.post("/api/v1/cuentas-anuales/2026/formular", json={})
    assert _get(fac, 20, "formulaciones").json()["items"] == []
    r = fac.post(
        "/api/v1/cuentas-anuales/2026/anular-formulacion",
        empresa_id=20,
        json={"motivo": "x"},
    )
    assert r.status_code == 409