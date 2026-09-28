"""T032: Imputación completa por HTTP — crear, trazar y rectificar (SPEC-017 US2).

Ciclo completo: crear centro → crear asiento con imputación (POSTED) →
verificar traza en `/imputaciones` → rectificar la imputación (ADJUSTMENT) →
el original queda intacto.
"""

from __future__ import annotations


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _asiento(centro_id) -> dict:
    return {
        "fecha": "2026-05-14",
        "concepto": "Gasto imputado",
        "lineas": [
            {"cuenta": "4300", "debe": "150.0000", "haber": "0", "centro_coste_id": str(centro_id)},
            {"cuenta": "5720", "debe": "0", "haber": "150.0000"},
        ],
    }


def test_ciclo_imputacion_y_rectificacion(costcenters_client):
    client, token, _ = costcenters_client
    org = client.post("/api/v1/centros", json={"codigo": "ORG", "nombre": "Origen", "tipo": "proyecto"}, headers=_hh(token, 10)).json()
    dst = client.post("/api/v1/centros", json={"codigo": "DST", "nombre": "Destino", "tipo": "proyecto"}, headers=_hh(token, 10)).json()

    r = client.post("/api/v1/asientos", json=_asiento(org["id"]), headers=_hh(token, 10))
    assert r.status_code == 201
    asiento = r.json()["id"]

    detalle = client.get(f"/api/v1/asientos/{asiento}", headers=_hh(token, 10)).json()
    linea = next(l for l in detalle["lineas"] if l["debe"] != "0.0000")
    assert linea["centro_coste_id"] == org["id"]

    r = client.get("/api/v1/imputaciones", params={"asiento_id": asiento}, headers=_hh(token, 10))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["codigo"] == "ORG"
    assert items[0]["linea_cuenta"] == "4300"
    assert items[0]["periodo"] == 5

    # Rectificar la imputación de la línea posteada
    r = client.post(
        f"/api/v1/asientos/{asiento}/lineas/{linea['id']}/rectificar-imputacion",
        json={"centro_coste_id": dst["id"]},
        headers=_hh(token, 10),
    )
    assert r.status_code == 201
    rectificado = r.json()
    assert rectificado["asiento_original_id"] == asiento
    assert rectificado["numero_asiento"] == 2

    # Original intacto (sigue en ORG)
    detalle = client.get(f"/api/v1/asientos/{asiento}", headers=_hh(token, 10)).json()
    lineas_org = [l for l in detalle["lineas"] if l["debe"] != "0.0000"]
    assert lineas_org[0]["centro_coste_id"] == org["id"]

    # El asiento nuevo es un ADJUSTMENT con 2 líneas: revert (ORG) y rebook (DST)
    nuevo = client.get(f"/api/v1/asientos/{rectificado['asiento_rectificativo_id']}", headers=_hh(token, 10)).json()
    assert nuevo["estado"] == "POSTED"
    assert len(nuevo["lineas"]) == 2
    centros_nuevo = {l["centro_coste_id"] for l in nuevo["lineas"]}
    assert centros_nuevo == {org["id"], dst["id"]}


def test_traza_filtrada_por_centro(costcenters_client):
    client, token, _ = costcenters_client
    c1 = client.post("/api/v1/centros", json={"codigo": "F1", "nombre": "F1", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    c2 = client.post("/api/v1/centros", json={"codigo": "F2", "nombre": "F2", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    a1 = client.post("/api/v1/asientos", json=_asiento(c1), headers=_hh(token, 10)).json()["id"]
    a2 = client.post("/api/v1/asientos", json=_asiento(c2), headers=_hh(token, 10)).json()["id"]

    r = client.get("/api/v1/imputaciones", params={"centro_id": c1}, headers=_hh(token, 10))
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["asiento_id"] == a1

    r = client.get("/api/v1/imputaciones", params={"centro_id": c2}, headers=_hh(token, 10))
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["asiento_id"] == a2


def test_rectificar_linea_sin_imputacion_409(costcenters_client):
    client, token, _ = costcenters_client
    # Asiento sin centro en ninguna línea
    r = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-05-14",
            "concepto": "Sin imputar",
            "lineas": [
                {"cuenta": "4300", "debe": "10.0000", "haber": "0"},
                {"cuenta": "5720", "debe": "0", "haber": "10.0000"},
            ],
        },
        headers=_hh(token, 10),
    )
    asiento = r.json()["id"]
    detalle = client.get(f"/api/v1/asientos/{asiento}", headers=_hh(token, 10)).json()
    linea = detalle["lineas"][0]
    centro = client.post("/api/v1/centros", json={"codigo": "CT", "nombre": "T", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]

    r = client.post(
        f"/api/v1/asientos/{asiento}/lineas/{linea['id']}/rectificar-imputacion",
        json={"centro_coste_id": centro},
        headers=_hh(token, 10),
    )
    assert r.status_code == 409
