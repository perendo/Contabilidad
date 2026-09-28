"""SPEC-018 T028: generacion completa de asientos desde plantilla (HTTP)."""

from uuid import uuid4


def _crear_mixta(c, empresa_id: int = 10) -> tuple[str, str]:
    variable_id = str(uuid4())
    cuerpo = {
        "nombre": "Mixta",
        "variables": [{"id": variable_id, "nombre": "importe", "es_requerida": True}],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "importe_fijo": "100.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "importe_fijo": "100.0000"},
            {"orden": 3, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "variable_id": variable_id},
            {"orden": 4, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "variable_id": variable_id},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", empresa_id=empresa_id, json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"], variable_id


def _crear_desbalanceada(c, empresa_id: int = 10) -> str:
    cuerpo = {
        "nombre": "Desbalanceada",
        "variables": [],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "importe_fijo": "100.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "importe_fijo": "50.0000"},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", empresa_id=empresa_id, json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def test_generacion_completa_y_correlativa(templates_client):
    c = templates_client
    plantilla_id, variable_id = _crear_mixta(c)

    primera = c.post(
        f"/api/v1/plantillas/{plantilla_id}/generar",
        json={"fecha_asiento": "2026-03-10", "variables": {variable_id: "100.0000"}},
    )
    assert primera.status_code == 201, primera.text
    datos = primera.json()
    asiento = datos["asiento"]
    assert asiento["estado"] == "POSTED"
    assert asiento["total_debe"] == asiento["total_haber"] == "200.0000"
    assert len(asiento["lineas"]) == 4
    assert datos["version_plantilla"] == 1
    assert datos["variables_aportadas"][variable_id] == "100.0000"
    numero_primero = asiento["numero_asiento"]

    segunda = c.post(
        f"/api/v1/plantillas/{plantilla_id}/generar",
        json={"fecha_asiento": "2026-03-11", "variables": {"importe": "250.0000"}},
    )
    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["asiento"]["numero_asiento"] == numero_primero + 1

    generados = c.get(10, f"/api/v1/plantillas/{plantilla_id}/generados")
    assert generados.status_code == 200
    assert generados.json()["total"] == 2
    assert all(item["plantilla_id"] == plantilla_id for item in generados.json()["items"])


def test_generacion_faltante_inactiva_y_desbalanceada(templates_client):
    c = templates_client
    plantilla_id, variable_id = _crear_mixta(c)

    faltante = c.post(
        f"/api/v1/plantillas/{plantilla_id}/generar",
        json={"fecha_asiento": "2026-03-10", "variables": {}},
    )
    assert faltante.status_code == 422, faltante.text
    assert faltante.json()["detail"]["code"] == "variables_faltantes"

    assert c.post(f"/api/v1/plantillas/{plantilla_id}/inactivar").status_code == 200
    inactiva = c.post(
        f"/api/v1/plantillas/{plantilla_id}/generar",
        json={"fecha_asiento": "2026-03-10", "variables": {variable_id: "10.0000"}},
    )
    assert inactiva.status_code == 409, inactiva.text
    assert inactiva.json()["detail"]["code"] == "plantilla_inactiva"

    desbalanceada = _crear_desbalanceada(c)
    descuadre = c.post(
        f"/api/v1/plantillas/{desbalanceada}/generar",
        json={"fecha_asiento": "2026-03-10", "variables": {}},
    )
    assert descuadre.status_code == 409, descuadre.text
    assert descuadre.json()["detail"]["code"] == "desbalanceo"


def test_ejercicio_cerrado_bloquea_generacion(templates_client):
    c = templates_client
    plantilla_id, variable_id = _crear_mixta(c)
    c.marcar_cerrado(10, 2026)
    cerrado = c.post(
        f"/api/v1/plantillas/{plantilla_id}/generar",
        json={"fecha_asiento": "2026-03-10", "variables": {variable_id: "10.0000"}},
    )
    assert cerrado.status_code == 409, cerrado.text
    assert cerrado.json()["detail"]["code"] == "ejercicio_cerrado"
