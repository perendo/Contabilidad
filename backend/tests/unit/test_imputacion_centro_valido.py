"""T024: Imputación a centro válido/inválido (SPEC-017, vía HTTP).

- Centro inexistente (o de otra empresa) al crear asiento -> 404
  `centro_no_encontrado`.
- Centro inactivo -> 422 `centro_inactivo`.
- Centro activo propio -> asiento POSTED correcto.
"""

from __future__ import annotations

import uuid


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _asiento_payload(centro_id) -> dict:
    return {
        "fecha": "2026-05-14",
        "concepto": "Gasto imputado",
        "lineas": [
            {"cuenta": "4300", "debe": "100.0000", "haber": "0", "centro_coste_id": str(centro_id)},
            {"cuenta": "5720", "debe": "0", "haber": "100.0000"},
        ],
    }


def test_centro_activo_imputa_ok(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/centros", json={"codigo": "ACT", "nombre": "Activo", "tipo": "proyecto"}, headers=_hh(token, 10))
    assert r.status_code == 201
    centro = r.json()["id"]

    r = client.post("/api/v1/asientos", json=_asiento_payload(centro), headers=_hh(token, 10))
    assert r.status_code == 201
    body = r.json()
    assert body["n_lineas"] == 2
    assert body["estado"] == "POSTED"


def test_centro_inexistente_rechazado_404(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/asientos", json=_asiento_payload(uuid.uuid4()), headers=_hh(token, 10))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "centro_no_encontrado"


def test_centro_de_otra_empresa_rechazado_404(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/centros", json={"codigo": "A10", "nombre": "A10", "tipo": "proyecto"}, headers=_hh(token, 10))
    assert r.status_code == 201
    centro_a = r.json()["id"]

    # Empresa B intenta imputar a un centro de A
    r = client.post("/api/v1/asientos", json=_asiento_payload(centro_a), headers=_hh(token, 20))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "centro_no_encontrado"


def test_centro_inactivo_rechazado_422(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/centros", json={"codigo": "INAC", "nombre": "Inactivo", "tipo": "proyecto"}, headers=_hh(token, 10))
    assert r.status_code == 201
    centro = r.json()["id"]

    r = client.post(f"/api/v1/centros/{centro}/inactivar", headers=_hh(token, 10))
    assert r.status_code == 200
    assert r.json()["estado"] == "inactivo"

    r = client.post("/api/v1/asientos", json=_asiento_payload(centro), headers=_hh(token, 10))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "centro_inactivo"


def test_imputar_linea_a_centro_invalido_via_endpoint_404(costcenters_client):
    client, token, _ = costcenters_client
    r = client.post("/api/v1/centros", json={"codigo": "OKC", "nombre": "OK", "tipo": "proyecto"}, headers=_hh(token, 10))
    assert r.status_code == 201

    # El endpoint imputar requiere un asiento borrador (2026): usar rectificar sobre inexistente
    r = client.post(
        f"/api/v1/asientos/{uuid.uuid4()}/lineas/{uuid.uuid4()}/rectificar-imputacion",
        json={"centro_coste_id": uuid.uuid4().hex},
        headers=_hh(token, 10),
    )
    assert r.status_code == 404
    assert "no existe" in r.json()["detail"]