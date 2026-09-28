"""SPEC-018 T036: aislamiento multi-tenant en la gestion de plantillas."""


def _plantilla(c, empresa_id: int = 10) -> str:
    cuerpo = {
        "nombre": "De la empresa A",
        "variables": [],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "importe_fijo": "10.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "importe_fijo": "10.0000"},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", empresa_id=empresa_id, json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def test_b_no_gestiona_ni_ve_generados_de_a(templates_client):
    c = templates_client
    plantilla_a = _plantilla(c, 10)
    generado = c.post(f"/api/v1/plantillas/{plantilla_a}/generar", json={"fecha_asiento": "2026-06-01", "variables": {}})
    assert generado.status_code == 201, generado.text

    assert c.patch(f"/api/v1/plantillas/{plantilla_a}", empresa_id=20, json={"nombre": "Robada"}).status_code == 404
    assert c.post(f"/api/v1/plantillas/{plantilla_a}/activar", empresa_id=20).status_code == 404
    assert c.post(f"/api/v1/plantillas/{plantilla_a}/inactivar", empresa_id=20).status_code == 404
    assert c.get(20, f"/api/v1/plantillas/{plantilla_a}/generados").status_code == 404


def test_generados_de_b_no_contienen_los_de_a(templates_client):
    c = templates_client
    plantilla_a = _plantilla(c, 10)
    plantilla_b = _plantilla(c, 20)
    c.post(f"/api/v1/plantillas/{plantilla_a}/generar", json={"fecha_asiento": "2026-06-01", "variables": {}})
    c.post(f"/api/v1/plantillas/{plantilla_b}/generar", empresa_id=20, json={"fecha_asiento": "2026-06-01", "variables": {}})

    generados_b = c.get(20, f"/api/v1/plantillas/{plantilla_b}/generados")
    assert generados_b.status_code == 200
    assert generados_b.json()["total"] == 1
    assert all(item["plantilla_id"] == plantilla_b for item in generados_b.json()["items"])
