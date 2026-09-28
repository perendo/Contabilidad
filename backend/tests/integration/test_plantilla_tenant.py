"""SPEC-018 T019: aislamiento multi-tenant de plantillas via API (US1)."""


def _cuerpo(c, empresa_id: int) -> dict:
    return {
        "nombre": "Plantilla privada",
        "variables": [],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "importe_fijo": "10.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "importe_fijo": "10.0000"},
        ],
    }


def test_b_no_ve_ni_edita_la_plantilla_de_a(templates_client):
    c = templates_client
    creada = c.post("/api/v1/plantillas", empresa_id=10, json=_cuerpo(c, 10))
    assert creada.status_code == 201, creada.text
    plantilla_id = creada.json()["id"]

    listado_b = c.get(20, "/api/v1/plantillas")
    assert listado_b.status_code == 200
    assert listado_b.json()["total"] == 0

    detalle_b = c.get(20, f"/api/v1/plantillas/{plantilla_id}")
    assert detalle_b.status_code == 404, detalle_b.text

    patch_b = c.patch(f"/api/v1/plantillas/{plantilla_id}", empresa_id=20, json={"nombre": "Robada"})
    assert patch_b.status_code == 404, patch_b.text

    inactivar_b = c.post(f"/api/v1/plantillas/{plantilla_id}/inactivar", empresa_id=20)
    assert inactivar_b.status_code == 404, inactivar_b.text

    listado_a = c.get(10, "/api/v1/plantillas")
    assert listado_a.json()["total"] == 1
    assert listado_a.json()["items"][0]["id"] == plantilla_id


def test_b_puede_crear_su_propia_plantilla_con_mismo_nombre(templates_client):
    c = templates_client
    nombre = "Plantilla compartida de nombre"
    a = c.post("/api/v1/plantillas", empresa_id=10, json={**_cuerpo(c, 10), "nombre": nombre})
    assert a.status_code == 201, a.text
    b = c.post("/api/v1/plantillas", empresa_id=20, json={**_cuerpo(c, 20), "nombre": nombre})
    assert b.status_code == 201, b.text
    assert a.json()["id"] != b.json()["id"]
