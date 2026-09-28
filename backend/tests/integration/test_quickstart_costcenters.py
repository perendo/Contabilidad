"""T045: Quickstart SPEC-017 — escenario completo de principio a fin por HTTP.

1. Alta de centros jerárquicos (auditable).
2. Asiento multilínea imputado a un centro.
3. Consulta del informe de costes con subtotales.
4. Rectificación de imputación conservando el original.
5. Exportación CSV.
"""

from __future__ import annotations


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_quickstart_costcenters(costcenters_client):
    client, token, _ = costcenters_client

    # 1. Árbol de centros
    marketing = client.post("/api/v1/centros", json={"codigo": "MK", "nombre": "Marketing", "tipo": "departamento"}, headers=_hh(token, 10)).json()["id"]
    campana = client.post("/api/v1/centros", json={"codigo": "CM", "nombre": "Campaña Verano", "tipo": "proyecto", "parent_id": marketing}, headers=_hh(token, 10)).json()["id"]

    # 2. Asiento imputado
    r = client.post(
        "/api/v1/asientos",
        json={
            "fecha": "2026-08-01",
            "concepto": "Publicidad campaña",
            "lineas": [
                {"cuenta": "6000", "debe": "4250.5000", "haber": "0", "centro_coste_id": campana},
                {"cuenta": "4100", "debe": "0", "haber": "4250.5000"},
            ],
        },
        headers=_hh(token, 10),
    )
    assert r.status_code == 201
    asiento = r.json()
    assert asiento["estado"] == "POSTED"
    assert asiento["total_debe"] == "4250.5000"

    # 3. Informe con subtotales
    r = client.get("/api/v1/informes/costes", params={"ejercicio": 2026, "centro_id": marketing}, headers=_hh(token, 10))
    assert r.status_code == 200
    informe = r.json()
    assert informe["totales"]["coste"] == "4250.5000"
    por_codigo = {f["codigo"]: f for f in informe["filas"]}
    assert por_codigo["MK"]["subtotal_debe"] == "4250.5000"
    assert por_codigo["CM"]["directo_debe"] == "4250.5000"

    # 4. Rectificar imputación (campaña -> marketing directo)
    detalle = client.get(f"/api/v1/asientos/{asiento['id']}", headers=_hh(token, 10)).json()
    linea = next(l for l in detalle["lineas"] if l["debe"] != "0.0000")
    r = client.post(
        f"/api/v1/asientos/{asiento['id']}/lineas/{linea['id']}/rectificar-imputacion",
        json={"centro_coste_id": marketing},
        headers=_hh(token, 10),
    )
    assert r.status_code == 201
    rectificado = r.json()
    assert rectificado["asiento_rectificativo_id"]

    # 5. Exportación CSV legible
    r = client.get("/api/v1/informes/costes/exportar", params={"ejercicio": 2026, "format": "csv"}, headers=_hh(token, 10))
    assert r.status_code == 200
    contenido = r.content.decode("utf-8-sig")
    assert "MK;Marketing" in contenido
    assert "4250.5000" in contenido
