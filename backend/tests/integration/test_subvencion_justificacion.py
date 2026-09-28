"""Flujo HTTP completo de subvenciones y justificación (SPEC-019 US1).

Cubre el ciclo crear subvención → imputar gasto por línea → informe de
justificación → exportación → desimputación → transición a justificada, todo a
través de la API `/api/v1` con la empresa activa de la sesión.
"""

from __future__ import annotations

import json as _json


def _gasto_linea(ns, empresa_id=10, importe="1000.0000", fecha="2026-05-10", concepto="Gasto"):
    """Crea un asiento de gasto vía API y devuelve (asiento_id, linea_debe_id)."""
    r = ns.post(
        "/api/v1/asientos",
        empresa_id,
        {
            "fecha": fecha,
            "concepto": concepto,
            "lineas": [
                {"cuenta": "6400", "debe": importe, "haber": "0", "detalle": "gasto"},
                {"cuenta": "5720", "debe": "0", "haber": importe, "detalle": "banco"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    detalle = ns.get(empresa_id, f"/api/v1/asientos/{r.json()['id']}")
    assert detalle.status_code == 200
    linea = next(l for l in detalle.json()["lineas"] if l["debe"] != "0.0000")
    return r.json()["id"], linea["id"]


def test_ciclo_crear_imputar_informe_exportar(ngo_client):
    ns = ngo_client
    r = ns.post(
        "/api/v1/subvenciones",
        10,
        {
            "entidad_concedente": "Ayuntamiento",
            "programa": "Voluntariado",
            "referencia": "INTEG",
            "importe_concedido": "1000.0000",
            "ejercicio": 2025,
        },
    )
    assert r.status_code == 201, r.text
    sub = r.json()
    sid = sub["id"]

    detalle = ns.get(10, f"/api/v1/subvenciones/{sid}")
    assert detalle.status_code == 200
    assert detalle.json()["importe_concedido"] == "1000.0000"
    assert detalle.json()["estado"] == "concedida"

    asiento_id, linea_id = _gasto_linea(ns, 10, "400.0000", "2026-05-10", "Gasto 1")
    g = ns.post(
        f"/api/v1/subvenciones/{sid}/gastos",
        10,
        {"asiento_id": asiento_id, "linea_id": linea_id, "importe_asignado": "400.0000", "partida": "P1"},
    )
    assert g.status_code == 201, g.text
    assert g.json()["gastado"] == "400.0000"
    assert g.json()["pendiente"] == "600.0000"

    informe = ns.get(10, f"/api/v1/informes/subvenciones/{sid}/justificacion")
    assert informe.status_code == 200
    data = informe.json()
    assert data["gastado"] == "400.0000"
    assert data["pendiente"] == "600.0000"
    assert len(data["detalle"]) == 1
    assert len(data["huella"]) == 64

    csv_r = ns.get(10, f"/api/v1/informes/subvenciones/{sid}/justificacion/exportar", formato="csv")
    assert csv_r.status_code == 200
    assert "text/csv" in csv_r.headers["content-type"]
    assert csv_r.content.startswith(b"\xef\xbb\xbfentidad;programa;referencia;")
    assert b"P1" in csv_r.content

    js = ns.get(10, f"/api/v1/informes/subvenciones/{sid}/justificacion/exportar", formato="json")
    assert js.status_code == 200
    payload = _json.loads(js.content)
    assert payload["gastado"] == "400.0000"

    d = ns.delete(f"/api/v1/subvenciones/{sid}/gastos/{g.json()['id']}", 10)
    assert d.status_code == 204

    detalle2 = ns.get(10, f"/api/v1/subvenciones/{sid}")
    assert detalle2.json()["gastado"] == "0.0000"


def test_flujo_justificar_evita_desimputar(ngo_client):
    ns = ngo_client
    sub = ns.post(
        "/api/v1/subvenciones",
        10,
        {"entidad_concedente": "Ayto", "programa": "Cursos", "importe_concedido": "500.0000", "ejercicio": 2025},
    ).json()
    sid = sub["id"]
    asiento_id, linea_id = _gasto_linea(ns, 10, "500.0000", "2026-06-01", "Gasto")
    g = ns.post(
        f"/api/v1/subvenciones/{sid}/gastos",
        10,
        {"asiento_id": asiento_id, "linea_id": linea_id, "importe_asignado": "500.0000"},
    ).json()

    e1 = ns.post(f"/api/v1/subvenciones/{sid}/estado", 10, {"estado": "en_curso"})
    assert e1.status_code == 200
    e2 = ns.post(f"/api/v1/subvenciones/{sid}/estado", 10, {"estado": "justificada"})
    assert e2.status_code == 200
    assert e2.json()["estado"] == "justificada"

    d = ns.delete(f"/api/v1/subvenciones/{sid}/gastos/{g['id']}", 10)
    assert d.status_code == 409
    assert "justificada" in d.json().get("detail", "")


def test_quickstart_excede_disponible(ngo_client):
    """Escenario 1 del quickstart: 2000 + 3500 sobre una concedida de 5000 → 409."""
    ns = ngo_client
    sub = ns.post(
        "/api/v1/subvenciones",
        10,
        {"entidad_concedente": "Fundación X", "programa": "Programa Y", "importe_concedido": "5000.0000", "ejercicio": 2026},
    ).json()
    sid = sub["id"]
    asiento_id, linea_id = _gasto_linea(ns, 10, "2000.0000", "2026-06-01", "Gasto 2000")

    g1 = ns.post(
        f"/api/v1/subvenciones/{sid}/gastos",
        10,
        {"asiento_id": asiento_id, "linea_id": linea_id, "importe_asignado": "2000.0000"},
    )
    assert g1.status_code == 201, g1.text

    asiento2_id, linea2_id = _gasto_linea(ns, 10, "4000.0000", "2026-06-02", "Gasto 4000")
    g2 = ns.post(
        f"/api/v1/subvenciones/{sid}/gastos",
        10,
        {"asiento_id": asiento2_id, "linea_id": linea2_id, "importe_asignado": "3500.0000"},
    )
    assert g2.status_code == 409  # excede_disponible: 2000 + 3500 > 5000

    informe = ns.get(10, f"/api/v1/informes/subvenciones/{sid}/justificacion").json()
    assert informe["gastado"] == "2000.0000"
    assert informe["pendiente"] == "3000.0000"


def test_actualizar_y_listar_subvenciones(ngo_client):
    ns = ngo_client
    sub = ns.post(
        "/api/v1/subvenciones",
        10,
        {"entidad_concedente": "Diputación", "programa": "Conciliación", "importe_concedido": "2000.0000", "ejercicio": 2025},
    ).json()
    sid = sub["id"]

    p = ns.patch(f"/api/v1/subvenciones/{sid}", 10, {"entidad_concedente": "Diputación Prov.", "observaciones": "Revisado"})
    assert p.status_code == 200, p.text
    assert p.json()["entidad_concedente"] == "Diputación Prov."

    lista = ns.get(10, "/api/v1/subvenciones", estado="concedida")
    assert lista.status_code == 200
    assert lista.json()["total"] == 1
    assert lista.json()["items"][0]["id"] == sid