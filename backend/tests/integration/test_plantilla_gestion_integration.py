"""SPEC-018 T035: gestion completa de versiones y estados (HTTP)."""


def _plantilla(c, importe: str = "100.0000") -> str:
    cuerpo = {
        "nombre": "Gestionable",
        "variables": [],
        "lineas": [
            {"orden": 1, "cuenta_id": c.cuenta(10, "6000"), "posicion": "debe", "importe_fijo": importe},
            {"orden": 2, "cuenta_id": c.cuenta(10, "5720"), "posicion": "haber", "importe_fijo": importe},
        ],
    }
    respuesta = c.post("/api/v1/plantillas", json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def _lineas(c, importe: str) -> list[dict]:
    return [
        {"orden": 1, "cuenta_id": c.cuenta(10, "6000"), "posicion": "debe", "importe_fijo": importe},
        {"orden": 2, "cuenta_id": c.cuenta(10, "5720"), "posicion": "haber", "importe_fijo": importe},
    ]


def test_editar_entre_generaciones_conserva_versiones(templates_client):
    c = templates_client
    plantilla_id = _plantilla(c, "100.0000")

    primera = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-05-01", "variables": {}})
    assert primera.status_code == 201, primera.text
    asiento_primero = primera.json()["asiento"]["id"]

    editada = c.patch(f"/api/v1/plantillas/{plantilla_id}", json={"lineas": _lineas(c, "400.0000")})
    assert editada.status_code == 200, editada.text
    assert editada.json()["version_actual"] == 2

    segunda = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-05-02", "variables": {}})
    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["version_plantilla"] == 2
    assert segunda.json()["asiento"]["total_debe"] == "400.0000"

    historico = c.get(10, f"/api/v1/plantillas/{plantilla_id}/generados")
    assert historico.status_code == 200
    asientos = {item["asiento_id"]: item["version_plantilla"] for item in historico.json()["items"]}
    assert asientos[asiento_primero] == 1
    assert asientos[segunda.json()["asiento_id"]] == 2


def test_inactivar_reactivar_y_borrado_no_permitido(templates_client):
    c = templates_client
    plantilla_id = _plantilla(c)

    assert c.post(f"/api/v1/plantillas/{plantilla_id}/inactivar").status_code == 200
    bloqueada = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-05-01", "variables": {}})
    assert bloqueada.status_code == 409, bloqueada.text

    assert c.post(f"/api/v1/plantillas/{plantilla_id}/activar").status_code == 200
    regenerada = c.post(f"/api/v1/plantillas/{plantilla_id}/generar", json={"fecha_asiento": "2026-05-01", "variables": {}})
    assert regenerada.status_code == 201, regenerada.text

    borrado = c.client.delete(f"/api/v1/plantillas/{plantilla_id}", headers=c.headers("admin", 10))
    assert borrado.status_code in (404, 405)
