"""Aislamiento multi-tenant de Gestión ONG a través de la API (constitución III).

Una subvención/caja de la empresa 10 es invisible (404 o listado vacío) desde la
empresa 20; los gastos no cruzan a otra subvención.
"""

from __future__ import annotations


def _gasto_linea(ns, empresa_id=10, importe="300.0000", fecha="2026-05-20"):
    r = ns.post(
        "/api/v1/asientos",
        empresa_id,
        {
            "fecha": fecha,
            "concepto": "Gasto ISO",
            "lineas": [
                {"cuenta": "6400", "debe": importe, "haber": "0", "detalle": "gasto"},
                {"cuenta": "5720", "debe": "0", "haber": importe, "detalle": "banco"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    detalle = ns.get(empresa_id, f"/api/v1/asientos/{r.json()['id']}")
    linea = next(l for l in detalle.json()["lineas"] if l["debe"] != "0.0000")
    return r.json()["id"], linea["id"]


def test_subvencion_invisible_cross_tenant(ngo_client):
    ns = ngo_client
    sub = ns.post(
        "/api/v1/subvenciones",
        10,
        {"entidad_concedente": "Ayto", "programa": "Voluntariado", "importe_concedido": "900.0000", "ejercicio": 2025},
    ).json()
    sid = sub["id"]

    detalle_10 = ns.get(10, f"/api/v1/subvenciones/{sid}")
    assert detalle_10.status_code == 200

    detalle_20 = ns.get(20, f"/api/v1/subvenciones/{sid}")
    assert detalle_20.status_code == 404

    lista_20 = ns.get(20, "/api/v1/subvenciones")
    assert lista_20.status_code == 200
    assert lista_20.json()["total"] == 0


def test_gasto_no_cruza_subvencion(ngo_client):
    ns = ngo_client
    sub = ns.post(
        "/api/v1/subvenciones",
        10,
        {"entidad_concedente": "Ayto", "programa": "Voluntariado", "importe_concedido": "900.0000", "ejercicio": 2025},
    ).json()

    asiento_20, linea_20 = _gasto_linea(ns, 20, "300.0000", "2026-05-25")
    g = ns.post(
        f"/api/v1/subvenciones/{sub['id']}/gastos",
        20,
        {"asiento_id": asiento_20, "linea_id": linea_20, "importe_asignado": "300.0000"},
    )
    assert g.status_code == 404  # subvención de la empresa 10 no visible desde la 20


def test_caja_invisible_cross_tenant(ngo_client):
    ns = ngo_client
    c570 = ns.subcuenta_570(10)
    caja = ns.post(
        "/api/v1/cajas", 10, {"nombre": "Caja 10", "cuenta_570_id": c570, "tipo": "caja"}
    )
    assert caja.status_code == 201, caja.text
    cid = caja.json()["id"]

    assert ns.get(10, f"/api/v1/cajas/{cid}").status_code == 200
    assert ns.get(20, f"/api/v1/cajas/{cid}").status_code == 404
    assert ns.get(20, "/api/v1/cajas").json()["total"] == 0

    arq = ns.post(
        f"/api/v1/cajas/{cid}/arqueos", 20, {"fecha": "2026-08-31", "efectivo_contado": "0.0000"}
    )
    assert arq.status_code == 404