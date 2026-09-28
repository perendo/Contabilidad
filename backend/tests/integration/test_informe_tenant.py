"""T042: Aislamiento del informe de costes entre empresas por HTTP (SPEC-017 III).

El informe de B ignoran los movimientos y centros de A; consultar el informe
con un `centro_id` de A bajo empresa B responde 404.
"""

from __future__ import annotations

import uuid


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _asiento(centro_id) -> dict:
    return {
        "fecha": "2026-08-01",
        "concepto": "Gasto",
        "lineas": [
            {"cuenta": "6000", "debe": "60.0000", "haber": "0", "centro_coste_id": str(centro_id)},
            {"cuenta": "5720", "debe": "0", "haber": "60.0000"},
        ],
    }


def test_informe_no_cruza_empresas(costcenters_client):
    client, token, _ = costcenters_client
    centro_a = client.post("/api/v1/centros", json={"codigo": "AISO", "nombre": "A", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    client.post("/api/v1/asientos", json=_asiento(centro_a), headers=_hh(token, 10))

    r = client.get("/api/v1/informes/costes", params={"ejercicio": 2026}, headers=_hh(token, 20))
    assert r.status_code == 200
    assert r.json()["n_filas"] == 0
    assert r.json()["totales"]["coste"] == "0.0000"

    r = client.get("/api/v1/informes/costes", params={"ejercicio": 2026}, headers=_hh(token, 10))
    assert r.json()["totales"]["coste"] == "60.0000"


def test_informe_con_centro_id_de_otra_empresa_404(costcenters_client):
    client, token, _ = costcenters_client
    centro_a = client.post("/api/v1/centros", json={"codigo": "ZID", "nombre": "Z", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]

    r = client.get(
        "/api/v1/informes/costes",
        params={"ejercicio": 2026, "centro_id": centro_a},
        headers=_hh(token, 20),
    )
    assert r.status_code == 404


def test_exportar_con_scope_de_otra_empresa_404(costcenters_client):
    client, token, _ = costcenters_client
    centro_a = client.post("/api/v1/centros", json={"codigo": "WID", "nombre": "W", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]

    r = client.get(
        "/api/v1/informes/costes/exportar",
        params={"ejercicio": 2026, "centro_id": centro_a, "format": "csv"},
        headers=_hh(token, 20),
    )
    assert r.status_code == 404


def test_informe_fechas_independientes_por_empresa(costcenters_client):
    client, token, _ = costcenters_client
    centro_a = client.post("/api/v1/centros", json={"codigo": "FA", "nombre": "FA", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    centro_b = client.post("/api/v1/centros", json={"codigo": "FB", "nombre": "FB", "tipo": "proyecto"}, headers=_hh(token, 20)).json()["id"]
    client.post("/api/v1/asientos", json=_asiento(centro_a), headers=_hh(token, 10))
    client.post("/api/v1/asientos", json=_asiento(centro_b), headers=_hh(token, 20))

    informe_a = client.get("/api/v1/informes/costes", params={"ejercicio": 2026}, headers=_hh(token, 10)).json()
    informe_b = client.get("/api/v1/informes/costes", params={"ejercicio": 2026}, headers=_hh(token, 20)).json()
    assert informe_a["totales"]["coste"] == "60.0000"
    assert informe_a["filas"][0]["codigo"] == "FA"
    assert informe_b["totales"]["coste"] == "60.0000"
    assert informe_b["filas"][0]["codigo"] == "FB"


def test_centro_uuid_invalido_404(costcenters_client):
    client, token, _ = costcenters_client
    r = client.get(
        "/api/v1/informes/costes",
        params={"ejercicio": 2026, "centro_id": uuid.uuid4()},
        headers=_hh(token, 10),
    )
    assert r.status_code == 404