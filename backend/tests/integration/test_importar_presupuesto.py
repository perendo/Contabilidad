"""SPEC-026 US1 · T017: importacion en lote del presupuesto.

Importa 5 lineas (CSV y JSON), verifica que quedan almacenadas y que el
listado las muestra con codigo de cuenta y centro resueltos. Comprueba tambien
la atomicidad: si una fila es invalida, la importacion se aborta entera.
"""

from __future__ import annotations

EJERCICIO = 2026


def _csv() -> str:
    return (
        "codigo_cuenta,centro,importe,tipo\n"
        "6400,,48000.0000,gasto\n"
        "6810,,12000.0000,gasto\n"
        "7000,,120000.0000,ingreso\n"
        "6000,CC-01,8000.0000,gasto\n"
        "6210,CC-01,25000.0000,gasto\n"
    )


def test_importar_csv_cinco_lineas(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        files={"file": ("presupuesto_2026.csv", _csv(), "text/csv")},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["importadas"] == 5
    assert cuerpo["errores"] == []

    listado = ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO)
    assert listado.status_code == 200
    datos = listado.json()
    assert datos["total"] == 5
    codigos = {item["codigo_cuenta"] for item in datos["items"]}
    assert codigos == {"6400", "6810", "7000", "6000", "6210"}
    with_centro = [i for i in datos["items"] if i["centro_coste_id"] is not None]
    assert len(with_centro) == 2
    assert all("CC-01" in (i["nombre_centro"] or "") for i in with_centro)


def test_importar_json_actualiza_y_no_duplica(presupuestos_client):
    ns = presupuestos_client
    cuerpo = {
        "ejercicio": EJERCICIO,
        "lineas": [
            {"codigo_cuenta": "6400", "importe": "50000.0000", "tipo": "gasto"},
            {"codigo_cuenta": "7000", "importe": "90000.0000", "tipo": "ingreso"},
        ],
    }
    primera = ns.post("/api/v1/presupuestos/importar", json=cuerpo)
    assert primera.status_code == 200, primera.text
    assert primera.json()["importadas"] == 2

    cuerpo["lineas"][0]["importe"] = "51000.0000"
    segunda = ns.post("/api/v1/presupuestos/importar", json=cuerpo)
    assert segunda.status_code == 200
    assert segunda.json()["importadas"] == 2

    listado = ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO).json()
    assert listado["total"] == 2
    por_cuenta = {i["codigo_cuenta"]: i["importe"] for i in listado["items"]}
    assert por_cuenta["6400"] == "51000.0000"


def test_importacion_invalida_se_aborta(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        json={
            "ejercicio": EJERCICIO,
            "lineas": [
                {"codigo_cuenta": "6400", "importe": "48000.0000", "tipo": "gasto"},
                {"codigo_cuenta": "9999", "importe": "1.0000"},
            ],
        },
    )
    assert respuesta.status_code == 422
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "importacion_invalida"
    assert detalle["importadas"] == 0
    assert detalle["errores"][0]["fila"] == 2
    assert "cuenta_no_encontrada" in detalle["errores"][0]["motivo"]

    assert ns.get("/api/v1/presupuestos", ejercicio=EJERCICIO).json()["total"] == 0


def test_importacion_tipo_incoherente_es_422(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        json={
            "ejercicio": EJERCICIO,
            "lineas": [{"codigo_cuenta": "6400", "importe": "1.0000", "tipo": "ingreso"}],
        },
    )
    assert respuesta.status_code == 422
    assert "tipo_incoherente" in respuesta.json()["detail"]["errores"][0]["motivo"]


def test_importacion_csv_con_separador_punto_y_coma(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        files={"file": ("p_2026.csv", "6400;CC-01;1500.0000;gasto\n", "text/csv")},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["importadas"] == 1


def test_importacion_csv_sin_ejercicio_es_422(presupuestos_client):
    """Sin columna `ejercicio`, campo de formulario ni ano en el nombre: 422."""
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/importar",
        files={"file": ("presupuesto.csv", "6400,,1500.0000,gasto\n", "text/csv")},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "parametro_invalido"


def test_listado_filtrado_por_centro_y_cuenta(presupuestos_client):
    ns = presupuestos_client
    ns.post(
        "/api/v1/presupuestos/importar",
        files={"file": ("presupuesto_2026.csv", _csv(), "text/csv")},
    )
    centro = ns.centros(10)["CC-01"]
    cuenta_6400 = ns.cuenta(10, "6400")

    solo_centro = ns.get(
        "/api/v1/presupuestos", ejercicio=EJERCICIO, centro_coste_id=str(centro)
    ).json()
    assert solo_centro["total"] == 2

    solo_cuenta = ns.get(
        "/api/v1/presupuestos", ejercicio=EJERCICIO, cuenta_id=cuenta_6400
    ).json()
    assert solo_cuenta["total"] == 1
    assert solo_cuenta["items"][0]["codigo_cuenta"] == "6400"


def test_post_crea_actualiza_y_devuelve_cuatro_decimales(presupuestos_client):
    ns = presupuestos_client
    cuenta_6400 = ns.cuenta(10, "6400")
    cuerpo = {
        "ejercicio": EJERCICIO,
        "cuenta_id": cuenta_6400,
        "centro_coste_id": None,
        "importe": "48000.0000",
        "tipo": "gasto",
    }
    primera = ns.post("/api/v1/presupuestos", json=cuerpo)
    assert primera.status_code == 200, primera.text
    assert primera.json()["importe"] == "48000.0000"
    assert primera.json()["tipo"] == "gasto"

    cuerpo["importe"] = "49000.5"
    segunda = ns.post("/api/v1/presupuestos", json=cuerpo)
    assert segunda.status_code == 200
    assert segunda.json()["id"] == primera.json()["id"]
    assert segunda.json()["importe"] == "49000.5000"


def test_duplicado_identico_por_api_es_422(presupuestos_client):
    ns = presupuestos_client
    cuerpo = {
        "ejercicio": EJERCICIO,
        "cuenta_id": ns.cuenta(10, "6400"),
        "importe": "48000.0000",
        "tipo": "gasto",
    }
    assert ns.post("/api/v1/presupuestos", json=cuerpo).status_code == 200
    repetido = ns.post("/api/v1/presupuestos", json=cuerpo)
    assert repetido.status_code == 422
    assert repetido.json()["detail"]["code"] == "duplicado_identico"


def test_cuenta_inapunteable_por_api_es_422(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "64"),
            "importe": "48000.0000",
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "cuenta_inapunteable"


def test_ejercicio_cerrado_rechaza_el_presupuesto(presupuestos_client):
    ns = presupuestos_client
    ns.marcar_cerrado(10, 2025)
    respuesta = ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": 2025,
            "cuenta_id": ns.cuenta(10, "6400"),
            "importe": "48000.0000",
        },
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "ejercicio_cerrado"


def test_rbac_read_only_no_puede_crear(presupuestos_client):
    ns = presupuestos_client
    lectura = ns.get("/api/v1/presupuestos", token_key="readonly")
    assert lectura.status_code == 200
    escritura = ns.post(
        "/api/v1/presupuestos",
        token_key="readonly",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "importe": "1.0000",
        },
    )
    assert escritura.status_code == 403
    assert "insuficiente" in str(escritura.json()["detail"])
