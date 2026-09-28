"""SPEC-018 T039: reproduccion de los escenarios de quickstart.md."""

from uuid import uuid4


def _crear(c, empresa_id: int = 10, nombre: str | None = None, variable_requerida: bool = True) -> tuple[str, str]:
    variable_id = str(uuid4())
    cuerpo = {
        "nombre": nombre or f"Quickstart {empresa_id}",
        "variables": [{"id": variable_id, "nombre": "importe", "es_requerida": variable_requerida}],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(empresa_id, "6000"), "posicion": "debe", "importe_fijo": "1000.0000"},
            {"orden": 2, "cuenta_id": c.cuenta(empresa_id, "5720"), "posicion": "haber", "variable_id": variable_id},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", empresa_id=empresa_id, json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"], variable_id


def test_quickstart_escenario_1_crear_y_aislar(templates_client):
    c = templates_client
    plantilla_id, _ = _crear(c, 10, "Pago proveedor")
    detalle = c.get(10, f"/api/v1/plantillas/{plantilla_id}")
    assert detalle.status_code == 200
    assert len(detalle.json()["lineas"]) == 2
    assert c.get(20, "/api/v1/plantillas").json()["total"] == 0


def test_quickstart_escenario_2_generar_balanceado(templates_client):
    c = templates_client
    plantilla_id, variable_id = _crear(c, 10)
    generado = c.post(
        f"/api/v1/plantillas/{plantilla_id}/generar",
        json={"fecha_asiento": "2026-08-01", "variables": {variable_id: "1000.0000"}},
    )
    assert generado.status_code == 201, generado.text
    asiento = generado.json()["asiento"]
    assert asiento["total_debe"] == asiento["total_haber"] == "1000.0000"
    assert asiento["numero_asiento"] == 1


def test_quickstart_escenario_3_bloqueos(templates_client):
    c = templates_client
    plantilla_id, variable_id = _crear(c, 10)
    faltante = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-08-01", "variables": {}})
    assert faltante.status_code == 422
    assert faltante.json()["detail"]["code"] == "variables_faltantes"

    descuadre = c.post(
        "/api/v1/plantillas",
        json={
            "nombre": "Descuadre",
            "variables": [],
            "lineas": [
                {"orden": 1, "cuenta_id": c.cuenta(10, "6000"), "posicion": "debe", "importe_fijo": "100.0000"},
                {"orden": 2, "cuenta_id": c.cuenta(10, "5720"), "posicion": "haber", "importe_fijo": "40.0000"},
            ],
        },
    )
    assert descuadre.status_code == 201
    no_cuadra = c.post(f"/api/v1/plantillas/{descuadre.json()['id']}/generar", json={"fecha_asiento": "2026-08-01", "variables": {}})
    assert no_cuadra.status_code == 409

    c.post(f"/api/v1/plantillas/{plantilla_id}/inactivar")
    inactiva = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-08-01", "variables": {variable_id: "10.0000"}})
    assert inactiva.status_code == 409
    assert inactiva.json()["detail"]["code"] == "plantilla_inactiva"

    c.post(f"/api/v1/plantillas/{plantilla_id}/activar")
    c.marcar_cerrado(10, 2026)
    cerrado = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-08-01", "variables": {variable_id: "1000.0000"}})
    assert cerrado.status_code == 409
    assert cerrado.json()["detail"]["code"] == "ejercicio_cerrado"


def test_quickstart_escenario_4_inmutabilidad(templates_client):
    c = templates_client
    plantilla_id, variable_id = _crear(c, 10)
    primero = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-09-01", "variables": {variable_id: "1000.0000"}})
    assert primero.status_code == 201, primero.text
    asiento_id = primero.json()["asiento"]["id"]

    editada = c.patch(
        f"/api/v1/plantillas/{plantilla_id}",
        json={
            "lineas": [
                {"orden": 1, "cuenta_id": c.cuenta(10, "6000"), "posicion": "debe", "importe_fijo": "2000.0000"},
                {"orden": 2, "cuenta_id": c.cuenta(10, "5720"), "posicion": "haber", "variable_id": variable_id},
            ]
        },
    )
    assert editada.status_code == 200
    assert editada.json()["version_actual"] == 2

    segundo = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-09-02", "variables": {variable_id: "2000.0000"}})
    assert segundo.status_code == 201
    assert segundo.json()["version_plantilla"] == 2
    assert segundo.json()["asiento"]["id"] != asiento_id


def test_quickstart_escenario_5_cuenta_invalida_en_edicion(templates_client):
    c = templates_client
    plantilla_id, variable_id = _crear(c, 10)
    patch = c.patch(
        f"/api/v1/plantillas/{plantilla_id}",
        json={
            "lineas": [
                {"orden": 1, "cuenta_id": 999999, "posicion": "debe", "importe_fijo": "10.0000"},
                {"orden": 2, "cuenta_id": c.cuenta(10, "5720"), "posicion": "haber", "variable_id": variable_id},
            ]
        },
    )
    assert patch.status_code == 422, patch.text
    assert patch.json()["detail"]["code"] == "cuenta_invalida"


def test_quickstart_escenario_6_aislamiento_total(templates_client):
    c = templates_client
    plantilla_a, variable_a = _crear(c, 10, "A")
    assert c.post(f"/api/v1/plantillas/{plantilla_a}/generar", json={"fecha_asiento": "2026-10-01", "variables": {variable_a: "1000.0000"}}).status_code == 201

    assert c.get(20, f"/api/v1/plantillas/{plantilla_a}").status_code == 404
    assert c.post(f"/api/v1/plantillas/{plantilla_a}/generar", empresa_id=20, json={"fecha_asiento": "2026-10-01", "variables": {variable_a: "1000.0000"}}).status_code == 404

    plantilla_b, variable_b = _crear(c, 20, "B")
    generado_b = c.post(f"/api/v1/plantillas/{plantilla_b}/generar", empresa_id=20, json={"fecha_asiento": "2026-10-01", "variables": {variable_b: "1000.0000"}})
    assert generado_b.status_code == 201
    assert generado_b.json()["asiento"]["numero_asiento"] == 1
