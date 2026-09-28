"""SPEC-018 T018: alta completa de plantillas a traves de la API HTTP."""

from uuid import uuid4


def _cuerpo(cuenta_debe: int, cuenta_haber: int, variable_id: str) -> dict:
    return {
        "nombre": "Pago proveedor",
        "descripcion": "Pago recurrente",
        "categoria": "tesoreria",
        "variables": [{"id": variable_id, "nombre": "importe", "es_requerida": True}],
        "lineas": [
            {"orden": 1, "cuenta_id": cuenta_debe, "posicion": "debe", "importe_fijo": "100.0000"},
            {"orden": 2, "cuenta_id": cuenta_haber, "posicion": "haber", "variable_id": variable_id},
        ],
    }


def test_alta_completa_detalle_y_edicion(templates_client):
    c = templates_client
    variable_id = str(uuid4())
    comunidad = _cuerpo(c.cuenta(10, "6000"), c.cuenta(10, "5720"), variable_id)

    respuesta = c.post("/api/v1/plantillas", json=comunidad)
    assert respuesta.status_code == 201, respuesta.text
    creada = respuesta.json()
    assert creada["version_actual"] == 1
    assert creada["estado"] == "activa"
    assert len(creada["lineas"]) == 2
    assert len(creada["variables"]) == 1
    assert creada["lineas"][1]["variable_id"] == variable_id

    detalle = c.get(10, f"/api/v1/plantillas/{creada['id']}")
    assert detalle.status_code == 200
    assert detalle.json()["nombre"] == "Pago proveedor"

    listado = c.get(10, "/api/v1/plantillas")
    assert listado.status_code == 200
    assert listado.json()["total"] == 1

    editada = c.patch(
        f"/api/v1/plantillas/{creada['id']}",
        json={
            "lineas": [
                {"orden": 1, "cuenta_id": c.cuenta(10, "6000"), "posicion": "debe", "importe_fijo": "250.0000"},
                {"orden": 2, "cuenta_id": c.cuenta(10, "5720"), "posicion": "haber", "variable_id": variable_id},
            ]
        },
    )
    assert editada.status_code == 200, editada.text
    assert editada.json()["version_actual"] == 2


def test_nombre_duplicado_devuelve_409(templates_client):
    c = templates_client
    comunidad = _cuerpo(c.cuenta(10, "6000"), c.cuenta(10, "5720"), str(uuid4()))
    assert c.post("/api/v1/plantillas", json=comunidad).status_code == 201
    duplicada = c.post("/api/v1/plantillas", json=comunidad)
    assert duplicada.status_code == 409, duplicada.text
    assert duplicada.json()["detail"]["code"] == "nombre_duplicado"
