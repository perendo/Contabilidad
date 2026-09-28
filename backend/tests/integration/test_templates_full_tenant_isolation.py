"""SPEC-018 T038: aislamiento multi-tenant completo (transversal)."""


def _cuerpo(c, empresa_id: int, nombre: str) -> dict:
    return {
        "nombre": nombre,
        "variables": [],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "importe_fijo": "10.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "importe_fijo": "10.0000"},
        ],
    }


def test_escenario_cross_empresa_completo(templates_client):
    c = templates_client
    creada_a = c.post("/api/v1/plantillas", empresa_id=10, json=_cuerpo(c, 10, "De A"))
    assert creada_a.status_code == 201, creada_a.text
    plantilla_a = creada_a.json()["id"]
    generado_a = c.post(f"/api/v1/plantillas/{plantilla_a}/generar", json={"fecha_asiento": "2026-07-01", "variables": {}})
    assert generado_a.status_code == 201, generado_a.text

    assert c.get(20, "/api/v1/plantillas").json()["total"] == 0
    assert c.get(20, f"/api/v1/plantillas/{plantilla_a}").status_code == 404
    assert c.patch(f"/api/v1/plantillas/{plantilla_a}", empresa_id=20, json={"nombre": "X"}).status_code == 404
    assert c.post(f"/api/v1/plantillas/{plantilla_a}/generar", empresa_id=20, json={"fecha_asiento": "2026-07-01", "variables": {}}).status_code == 404
    assert c.get(20, f"/api/v1/plantillas/{plantilla_a}/generados").status_code == 404

    creada_b = c.post("/api/v1/plantillas", empresa_id=20, json=_cuerpo(c, 20, "De B"))
    assert creada_b.status_code == 201, creada_b.text
    generado_b = c.post(f"/api/v1/plantillas/{creada_b.json()['id']}/generar", empresa_id=20, json={"fecha_asiento": "2026-07-01", "variables": {}})
    assert generado_b.status_code == 201, generado_b.text
    assert generado_b.json()["asiento"]["numero_asiento"] == 1


def test_cuenta_de_a_no_sirve_en_plantilla_de_b(templates_client):
    c = templates_client
    cuerpo = {
        "nombre": "Cuenta ajena",
        "variables": [],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(10, "6000"), "posicion": "debe", "importe_fijo": "10.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(10, "5720"), "posicion": "haber", "importe_fijo": "10.0000"},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", empresa_id=20, json=cuerpo)
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"]["code"] == "cuenta_invalida"
