"""SPEC-018 T029: aislamiento multi-tenant de la generacion (US2)."""

from uuid import uuid4


def _crear(c, empresa_id: int) -> tuple[str, str]:
    variable_id = str(uuid4())
    cuerpo = {
        "nombre": f"Plantilla {empresa_id}",
        "variables": [{"id": variable_id, "nombre": "importe"}],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "variable_id": variable_id},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "variable_id": variable_id},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", empresa_id=empresa_id, json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"], variable_id


def test_b_no_puede_generar_desde_la_plantilla_de_a(templates_client):
    c = templates_client
    plantilla_a, variable_a = _crear(c, 10)

    generado_a = c.post(
        f"/api/v1/plantillas/{plantilla_a}/generar",
        json={"fecha_asiento": "2026-03-10", "variables": {variable_a: "10.0000"}},
    )
    assert generado_a.status_code == 201, generado_a.text

    generar_b = c.post(
        f"/api/v1/plantillas/{plantilla_a}/generar",
        empresa_id=20,
        json={"fecha_asiento": "2026-03-10", "variables": {variable_a: "10.0000"}},
    )
    assert generar_b.status_code == 404, generar_b.text

    generados_b = c.get(20, f"/api/v1/plantillas/{plantilla_a}/generados")
    assert generados_b.status_code == 404, generados_b.text


def test_numeracion_independiente_por_empresa(templates_client):
    c = templates_client
    plantilla_a, variable_a = _crear(c, 10)
    plantilla_b, variable_b = _crear(c, 20)

    a1 = c.post(f"/api/v1/plantillas/{plantilla_a}/generar", json={"fecha_asiento": "2026-03-10", "variables": {variable_a: "10.0000"}})
    a2 = c.post(f"/api/v1/plantillas/{plantilla_a}/generar", json={"fecha_asiento": "2026-03-11", "variables": {variable_a: "20.0000"}})
    b1 = c.post(f"/api/v1/plantillas/{plantilla_b}/generar", empresa_id=20, json={"fecha_asiento": "2026-03-10", "variables": {variable_b: "30.0000"}})
    assert a1.status_code == 201 and a2.status_code == 201 and b1.status_code == 201

    assert a1.json()["asiento"]["numero_asiento"] == 1
    assert a2.json()["asiento"]["numero_asiento"] == 2
    assert b1.json()["asiento"]["numero_asiento"] == 1
