"""T041: Informe de costes completo por HTTP + exportación (SPEC-017 US3).

Los endpoints `/api/v1/informes/costes` agregan por centro con 4 decimales;
`/exportar?format=csv` devuelve un CSV con BOM y delimitador `;`.
"""

from __future__ import annotations


def _hh(token, empresa: int) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _asiento(centro_id, importe: str, lado: str) -> dict:
    if lado == "coste":
        l1 = {"cuenta": "6000", "debe": importe, "haber": "0", "centro_coste_id": str(centro_id)}
        l2 = {"cuenta": "5720", "debe": "0", "haber": importe}
    else:
        l1 = {"cuenta": "7000", "debe": "0", "haber": importe, "centro_coste_id": str(centro_id)}
        l2 = {"cuenta": "5720", "debe": importe, "haber": "0"}
    return {"fecha": "2026-07-01", "concepto": lado, "lineas": [l1, l2]}


def test_informe_por_http_con_subtotales(costcenters_client):
    client, token, _ = costcenters_client
    padre = client.post("/api/v1/centros", json={"codigo": "INF", "nombre": "Informe", "tipo": "departamento"}, headers=_hh(token, 10)).json()["id"]
    hijo = client.post("/api/v1/centros", json={"codigo": "INFH", "nombre": "Informe H", "tipo": "proyecto", "parent_id": padre}, headers=_hh(token, 10)).json()["id"]

    r = client.post("/api/v1/asientos", json=_asiento(hijo, "120.0000", "coste"), headers=_hh(token, 10))
    assert r.status_code == 201

    r = client.get("/api/v1/informes/costes", params={"ejercicio": 2026, "centro_id": padre}, headers=_hh(token, 10))
    assert r.status_code == 200
    body = r.json()
    assert body["n_filas"] == 2
    por_codigo = {f["codigo"]: f for f in body["filas"]}
    assert por_codigo["INF"]["subtotal_debe"] == "120.0000"
    assert por_codigo["INFH"]["directo_debe"] == "120.0000"
    assert body["totales"]["coste"] == "120.0000"
    assert body["totales"]["ingreso"] == "0.0000"


def test_exportar_csv(costcenters_client):
    client, token, _ = costcenters_client
    centro = client.post("/api/v1/centros", json={"codigo": "CSV", "nombre": "CSV", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    client.post("/api/v1/asientos", json=_asiento(centro, "99.9900", "coste"), headers=_hh(token, 10))

    r = client.get("/api/v1/informes/costes/exportar", params={"ejercicio": 2026, "format": "csv"}, headers=_hh(token, 10))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    contenido = r.content.decode("utf-8-sig")  # BOM al inicio
    cabecera = contenido.splitlines()[0]
    assert cabecera == "centro_id;codigo;nombre;parent_id;directo_debe;directo_haber;hijos_debe;hijos_haber;subtotal_debe;subtotal_haber;subtotal"
    assert "CSV;CSV;;99.9900" in contenido


def test_exportar_json(costcenters_client):
    client, token, _ = costcenters_client
    centro = client.post("/api/v1/centros", json={"codigo": "JSN", "nombre": "JSON", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    client.post("/api/v1/asientos", json=_asiento(centro, "5.0000", "coste"), headers=_hh(token, 10))

    r = client.get("/api/v1/informes/costes/exportar", params={"ejercicio": 2026, "format": "json"}, headers=_hh(token, 10))
    assert r.status_code == 200
    import json as _json

    data = _json.loads(r.content.decode("utf-8"))
    assert data["totales"]["coste"] == "5.0000"


def test_informe_tipo_filtro_por_http(costcenters_client):
    client, token, _ = costcenters_client
    centro = client.post("/api/v1/centros", json={"codigo": "TYP", "nombre": "Tipo", "tipo": "proyecto"}, headers=_hh(token, 10)).json()["id"]
    client.post("/api/v1/asientos", json=_asiento(centro, "30.0000", "coste"), headers=_hh(token, 10))
    client.post("/api/v1/asientos", json=_asiento(centro, "7.0000", "ingreso"), headers=_hh(token, 10))

    r_costes = client.get("/api/v1/informes/costes", params={"ejercicio": 2026, "tipo": "coste"}, headers=_hh(token, 10))
    assert r_costes.json()["totales"]["coste"] == "30.0000"
    assert r_costes.json()["totales"]["ingreso"] == "0.0000"

    r_ingresos = client.get("/api/v1/informes/costes", params={"ejercicio": 2026, "tipo": "ingreso"}, headers=_hh(token, 10))
    assert r_ingresos.json()["totales"]["ingreso"] == "7.0000"
    assert r_ingresos.json()["totales"]["coste"] == "0.0000"


def test_informe_periodo_invalido_422(costcenters_client):
    import uuid as _uuid

    client, token, _ = costcenters_client
    r = client.get(
        "/api/v1/informes/costes",
        params={"ejercicio": 2026, "fecha_desde": "2026-10-01", "fecha_hasta": "2026-01-01", "centro_id": _uuid.uuid4()},
        headers=_hh(token, 10),
    )
    assert r.status_code == 422