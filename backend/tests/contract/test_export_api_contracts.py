"""Contrato de la API de exportaciones (SPEC-029 T028/T037/T046).

Parte 1 (T028 · US1): 201/422/401/403 del POST, 200/404 del GET detalle y 409
del GET descarga cuando la exportacion no esta `lista`.
Parte 2 (T037 · US2): 200 con `integro` true/false, 404 cross-tenant y 422 si el
identificador no es valido.
Parte 3 (T046 · US3): 200/422 del GET /sii y 201/422 del POST tipo=SII segun la
configuracion de la empresa.
"""

from __future__ import annotations

import uuid

import pytest

RUTAS = "/api/v1/exportaciones"


# --- Parte 1 · US1 (T028) --------------------------------------------------


def test_post_crea_la_exportacion(export_client) -> None:
    respuesta = export_client.post(RUTAS, {"tipo": "INTEGRAL"})
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    for clave in (
        "exportacion_id",
        "numero_exportacion",
        "tipo",
        "estado",
        "ejercicio_desde",
        "ejercicio_hasta",
        "sha256",
        "tamano_bytes",
        "n_bloques",
        "manifiesto",
    ):
        assert clave in cuerpo, clave
    assert cuerpo["manifiesto"]["formato_version"] == "1.0.0"
    assert all("bloque" in b and "conteo_registros" in b for b in cuerpo["manifiesto"]["bloques"])


def test_post_sin_body_usa_integral(export_client) -> None:
    respuesta = export_client.post(RUTAS)
    assert respuesta.status_code == 201
    assert respuesta.json()["tipo"] == "INTEGRAL"


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"tipo": "OTRO"},
        {"tipo": "INTEGRAL", "ejercicio_desde": 2026, "ejercicio_hasta": 2025},
        {"tipo": "INTEGRAL", "ejercicio_desde": 2025},
        {"tipo": "INTEGRAL", "ejercicio_desde": 1999},
    ],
)
def test_post_devuelve_422_en_validaciones_de_negocio(export_client, cuerpo) -> None:
    respuesta = export_client.post(RUTAS, cuerpo)
    assert respuesta.status_code == 422
    assert "detail" in respuesta.json()


def test_post_401_sin_autenticacion(export_client) -> None:
    respuesta = export_client.client.post(RUTAS, json={"tipo": "INTEGRAL"})
    assert respuesta.status_code == 401


def test_post_403_sin_contexto_de_empresa(export_client) -> None:
    respuesta = export_client.client.post(
        RUTAS,
        json={"tipo": "INTEGRAL"},
        headers={"Authorization": f"Bearer {export_client.tokens['admin']}"},
    )
    assert respuesta.status_code == 403


def test_post_403_para_rol_sin_permiso_de_crear(export_client) -> None:
    """READ_ONLY tiene `ver` pero no `crear` en el modulo `export`."""
    respuesta = export_client.post(RUTAS, {"tipo": "INTEGRAL"}, token_key="readonly")
    assert respuesta.status_code == 403


def test_accountant_si_puede_crear(export_client) -> None:
    respuesta = export_client.post(
        RUTAS, {"tipo": "INTEGRAL"}, token_key="accountant"
    )
    assert respuesta.status_code == 201, respuesta.text


def test_get_listado_contrato(export_client) -> None:
    export_client.post(RUTAS, {"tipo": "INTEGRAL"})
    respuesta = export_client.get(RUTAS)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert {"items", "total", "page"} <= set(cuerpo)
    assert cuerpo["total"] == 1
    item = cuerpo["items"][0]
    for clave in (
        "exportacion_id",
        "numero_exportacion",
        "tipo",
        "estado",
        "ejercicio_desde",
        "ejercicio_hasta",
        "created_at",
        "sha256",
        "tamano_bytes",
        "n_bloques",
    ):
        assert clave in item, clave


def test_get_detalle_200_y_404(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    detalle = export_client.get(f"{RUTAS}/{exportacion_id}")
    assert detalle.status_code == 200
    cuerpo = detalle.json()
    assert cuerpo["manifiesto"]["sha256_fichero"] == cuerpo["sha256"]
    assert cuerpo["manifiesto"]["tenant_id"] == 10
    assert len(cuerpo["manifiesto"]["bloques"]) == cuerpo["manifiesto"]["n_bloques"]
    inexistente = export_client.get(f"{RUTAS}/{uuid.uuid4()}")
    assert inexistente.status_code == 404
    assert inexistente.json()["detail"]["code"] == "exportacion_no_encontrada"


def test_get_detalle_404_cross_tenant(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    assert export_client.get(f"{RUTAS}/{exportacion_id}", empresa_id=20).status_code == 404


def test_get_descarga_200_con_cabeceras(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    respuesta = export_client.get(f"{RUTAS}/{exportacion_id}/descarga")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/zip"
    disposicion = respuesta.headers["content-disposition"]
    assert disposicion.startswith("attachment;")
    assert 'filename="export_10_1_' in disposicion


def test_get_descarga_409_si_no_esta_lista(export_client) -> None:
    from datetime import datetime, timezone

    from models.export.exportacion import EstadoExportacion, Exportacion

    identificador = uuid.uuid4()

    async def _crear(sesion):
        sesion.add(
            Exportacion(
                id=identificador,
                empresa_id=10,
                anio_creacion=2026,
                numero_exportacion=97,
                tipo="INTEGRAL",
                estado=EstadoExportacion.en_proceso,
                created_at=datetime.now(timezone.utc),
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_crear))
    respuesta = export_client.get(f"{RUTAS}/{identificador}/descarga")
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "exportacion_no_descargable"


def test_get_descarga_404_cross_tenant_e_inexistente(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    assert export_client.get(
        f"{RUTAS}/{exportacion_id}/descarga", empresa_id=20
    ).status_code == 404
    assert export_client.get(f"{RUTAS}/{uuid.uuid4()}/descarga").status_code == 404


# --- Parte 2 · US2 (T037) --------------------------------------------------


def test_verificar_200_con_integro_true(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    respuesta = export_client.post(f"{RUTAS}/{exportacion_id}/verificar")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["integro"] is True
    assert cuerpo["diferencias"] == []
    assert cuerpo["sha256_calculado"] == cuerpo["sha256_manifiesto"]
    assert {"bloques"} <= set(cuerpo)


def test_verificar_200_con_integro_false(export_client) -> None:
    """`integro=false` se puede devolver si el blob se altera por debajo."""
    import hashlib

    from services.export.verificar import verificar_contenido

    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    original = export_client.get(f"{RUTAS}/{exportacion_id}/descarga").content
    veredicto = verificar_contenido(
        original + b"basura", 10, hashlib.sha256(original).hexdigest()
    )
    assert veredicto["integro"] is False
    assert {d["tipo"] for d in veredicto["diferencias"]} >= {"huella_fichero"}


def test_verificar_404_cross_tenant(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    respuesta = export_client.post(
        f"{RUTAS}/{exportacion_id}/verificar", empresa_id=20
    )
    assert respuesta.status_code == 404


def test_verificar_422_identificador_invalido(export_client) -> None:
    respuesta = export_client.post(f"{RUTAS}/no-es-uuid/verificar")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "parametro_invalido"


def test_verificar_401_sin_autenticacion(export_client) -> None:
    export_client.post(RUTAS, {"tipo": "INTEGRAL"})
    respuesta = export_client.client.post(f"{RUTAS}/{uuid.uuid4()}/verificar")
    assert respuesta.status_code == 401


# --- Parte 3 · US3 (T046) --------------------------------------------------


def test_get_sii_200_para_exportacion_sii(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "SII"}).json()["exportacion_id"]
    respuesta = export_client.get(f"{RUTAS}/{exportacion_id}/sii")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert {"obligado_sii", "sin_anexo", "clave_regimen"} <= set(cuerpo["config"])
    nombres = {b["nombre"] for b in cuerpo["bloques_sii"]}
    assert nombres == {"facturas_emitidas", "facturas_recibidas"}
    for bloque in cuerpo["bloques_sii"]:
        assert bloque["conteo"] == len(bloque["registros"])
        for registro in bloque["registros"]:
            assert "NIF" in registro and "ImporteTotal" in registro


def test_get_sii_422_para_exportacion_integral(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    respuesta = export_client.get(f"{RUTAS}/{exportacion_id}/sii")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "exportacion_no_sii"


def test_get_sii_404_cross_tenant_e_inexistente(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "SII"}).json()["exportacion_id"]
    assert export_client.get(
        f"{RUTAS}/{exportacion_id}/sii", empresa_id=20
    ).status_code == 404
    assert export_client.get(f"{RUTAS}/{uuid.uuid4()}/sii").status_code == 404


def test_post_sii_201_con_configuracion(export_client) -> None:
    respuesta = export_client.post(RUTAS, {"tipo": "SII"})
    assert respuesta.status_code == 201
    assert respuesta.json()["tipo"] == "SII"


def test_post_sii_422_sin_configuracion(export_client) -> None:
    respuesta = export_client.post(RUTAS, {"tipo": "SII"}, empresa_id=20)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "sin_configuracion_sii"


def test_config_sii_get_y_put(export_client) -> None:
    assert export_client.get(f"{RUTAS}/sii/config").status_code == 200
    guardado = export_client.put(
        f"{RUTAS}/sii/config", {"obligado_sii": True, "clave_regimen": "17"}
    )
    assert guardado.status_code == 200
    assert guardado.json() == {
        "obligado_sii": True,
        "sin_anexo": False,
        "clave_regimen": "17",
        "entidad_representante_id": None,
        "fecha_alta": None,
    }


def test_config_sii_put_403_para_readonly(export_client) -> None:
    respuesta = export_client.put(
        f"{RUTAS}/sii/config", {"clave_regimen": "01"}, token_key="readonly"
    )
    assert respuesta.status_code == 403


def test_ruta_estatica_sii_no_choca_con_el_uuid(export_client) -> None:
    """`/sii/config` se declara antes que `/{exportacion_id}`."""
    assert export_client.get(f"{RUTAS}/sii/config").status_code == 200
    assert export_client.get(f"{RUTAS}/sii").status_code == 422


def test_todos_los_errores_de_negocio_traen_code_y_detail(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    for respuesta in (
        export_client.get(f"{RUTAS}/{uuid.uuid4()}"),
        export_client.post(f"{RUTAS}/{uuid.uuid4()}/verificar", empresa_id=20),
        export_client.get(f"{RUTAS}/{exportacion_id}/sii"),
    ):
        detalle = respuesta.json()["detail"]
        assert isinstance(detalle, dict)
        assert {"code", "detail"} <= set(detalle)
