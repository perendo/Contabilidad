"""SPEC-018 T041: correlatividad de la numeracion de asientos generados."""


def _plantilla(c, empresa_id: int = 10, nombre: str = "Correlativa") -> str:
    cuerpo = {
        "nombre": nombre,
        "variables": [],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "importe_fijo": "5.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "importe_fijo": "5.0000"},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", empresa_id=empresa_id, json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def test_correlatividad_sin_saltos_por_ejercicio(templates_client):
    c = templates_client
    plantilla_id = _plantilla(c)

    numeros = []
    for dia in (1, 2, 3):
        generado = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": f"2026-11-0{dia}", "variables": {}})
        assert generado.status_code == 201, generado.text
        numeros.append(generado.json()["asiento"]["numero_asiento"])
    assert numeros == [1, 2, 3]

    otro_ejercicio = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2027-01-15", "variables": {}})
    assert otro_ejercicio.status_code == 201, otro_ejercicio.text
    assert otro_ejercicio.json()["asiento"]["numero_asiento"] == 1


def test_correlatividad_independiente_por_empresa(templates_client):
    c = templates_client
    plantilla_a = _plantilla(c, 10, "A")
    plantilla_b = _plantilla(c, 20, "B")
    for _ in range(2):
        assert c.post(f"/api/v1/plantillas/{plantilla_a}/generar", json={"fecha_asiento": "2026-12-01", "variables": {}}).status_code == 201
    generado_b = c.post(f"/api/v1/plantillas/{plantilla_b}/generar", empresa_id=20, json={"fecha_asiento": "2026-12-01", "variables": {}})
    assert generado_b.status_code == 201
    assert generado_b.json()["asiento"]["numero_asiento"] == 1
