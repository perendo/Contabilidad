"""Escenarios del quickstart de SPEC-029 (T049).

Reproduce los 6 escenarios de `specs/029-export-integral/quickstart.md` sobre la
API HTTP, con las mismas comprobaciones que el documento.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

RUTAS = "/api/v1/exportaciones"
CAMPOS_SII = {
    "NIF",
    "NombreRazon",
    "TipoFactura",
    "FechaOperacion",
    "FechaExpedicion",
    "NumeroFactura",
    "ClaveRegimen",
    "BaseImponible",
    "TipoImpositivo",
    "CuotaRepercutida",
    "ImporteTotal",
    "EstadoCuadre",
}


# --- Scenario 1 · exportar el tenant completo -------------------------------


def test_scenario_1_exportar_el_tenant_completo(export_client) -> None:
    respuesta = export_client.post(RUTAS, {"tipo": "INTEGRAL"})
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "lista"
    assert len(cuerpo["sha256"]) == 64
    assert cuerpo["tamano_bytes"] > 0
    assert cuerpo["n_bloques"] >= 17
    assert len(cuerpo["manifiesto"]["bloques"]) >= 17

    descarga = export_client.get(f"{RUTAS}/{cuerpo['exportacion_id']}/descarga")
    assert descarga.status_code == 200
    assert descarga.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(descarga.content), "r") as archivo:
        nombres = sorted(archivo.namelist())
        assert "manifest.json" in nombres
        assert sum(1 for n in nombres if n.startswith("bloques/")) >= 17
        manifiesto = json.loads(archivo.read("manifest.json").decode("utf-8"))
    assert len(manifiesto["bloques"]) == manifiesto["n_bloques"]
    assert manifiesto["tenant_id"] == 10
    assert hashlib.sha256(descarga.content).hexdigest() == cuerpo["sha256"]


# --- Scenario 2 · verificar la integridad -----------------------------------


def test_scenario_2_verificar_la_integridad(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()[
        "exportacion_id"
    ]
    veredicto = export_client.post(f"{RUTAS}/{exportacion_id}/verificar")
    assert veredicto.status_code == 200
    datos = veredicto.json()
    assert datos["integro"] is True
    assert datos["sha256_calculado"] == datos["sha256_manifiesto"]

    descarga = export_client.get(f"{RUTAS}/{exportacion_id}/descarga").content
    # Verificacion local con el manifiesto: la huella del contenido cuadra.
    with zipfile.ZipFile(io.BytesIO(descarga), "r") as archivo:
        manifiesto = json.loads(archivo.read("manifest.json").decode("utf-8"))
    from services.export.verificar import verificar_contenido

    assert (
        verificar_contenido(descarga, 10, hashlib.sha256(descarga).hexdigest())[
            "sha256_contenido"
        ]
        == manifiesto["sha256_contenido"]
    )


# --- Scenario 3 · filtro por rango de ejercicios ----------------------------


def test_scenario_3_filtro_por_rango(export_client) -> None:
    cuerpo = export_client.post(
        RUTAS, {"tipo": "INTEGRAL", "ejercicio_desde": 2025, "ejercicio_hasta": 2025}
    ).json()
    assert cuerpo["estado"] == "lista"
    exportacion_id = cuerpo["exportacion_id"]
    detalle = export_client.get(f"{RUTAS}/{exportacion_id}").json()["manifiesto"]
    for nombre in ("asientos", "facturas", "vencimientos"):
        linea = next(b for b in detalle["bloques"] if b["bloque"] == nombre)
        assert linea["ejercicio_min"] == linea["ejercicio_max"] == 2025, nombre
    for nombre in ("plan_cuentas", "terceros", "configuracion"):
        linea = next(b for b in detalle["bloques"] if b["bloque"] == nombre)
        assert linea["conteo_registros"] > 0, nombre
    ficheros = export_client.abrir(
        export_client.get(f"{RUTAS}/{exportacion_id}/descarga")
    )
    asientos = json.loads(ficheros["bloques/003_asientos.json"].decode("utf-8"))
    assert {r["ejercicio"] for r in asientos["registros"]} == {2025}


# --- Scenario 4 · aislamiento multi-empresa ---------------------------------


def test_scenario_4_aislamiento_multi_empresa(export_client) -> None:
    exportacion_id = export_client.post(
        RUTAS, {"tipo": "INTEGRAL"}, empresa_id=10
    ).json()["exportacion_id"]
    assert export_client.get(
        f"{RUTAS}/{exportacion_id}/descarga", empresa_id=20
    ).status_code == 404
    assert export_client.get(
        f"{RUTAS}/{exportacion_id}", empresa_id=20
    ).status_code == 404
    assert export_client.post(
        f"{RUTAS}/{exportacion_id}/verificar", empresa_id=20
    ).status_code == 404
    ficheros = export_client.abrir(
        export_client.get(f"{RUTAS}/{exportacion_id}/descarga", empresa_id=10)
    )
    for ruta, crudo in ficheros.items():
        if not ruta.endswith(".json") or ruta == "manifest.json":
            continue
        for registro in json.loads(crudo.decode("utf-8")).get("registros", []):
            if "empresa_id" in registro:
                assert registro["empresa_id"] == 10, ruta


# --- Scenario 5 · bloque SII (opcional) -------------------------------------


def test_scenario_5_bloque_sii(export_client) -> None:
    exportacion_id = export_client.post(RUTAS, {"tipo": "SII"}).json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"{RUTAS}/{exportacion_id}/descarga")
    )
    assert "bloques/datos_sii/facturas_emitidas.json" in ficheros
    assert "bloques/datos_sii/facturas_recibidas.json" in ficheros
    payload = export_client.get(f"{RUTAS}/{exportacion_id}/sii")
    assert payload.status_code == 200
    for bloque in payload.json()["bloques_sii"]:
        for registro in bloque["registros"]:
            assert CAMPOS_SII <= set(registro)


# --- Scenario 6 · tenant con datos incompletos ------------------------------


def test_scenario_6_tenant_con_datos_incompletos(export_client) -> None:
    cuerpo = export_client.post(RUTAS, {"tipo": "INTEGRAL"}).json()
    assert cuerpo["estado"] == "lista"
    detalle = export_client.get(
        f"{RUTAS}/{cuerpo['exportacion_id']}"
    ).json()["manifiesto"]
    conteos = {b["bloque"]: b["conteo_registros"] for b in detalle["bloques"]}
    # Sin remesas ni amortizaciones: presentes con conteo 0.
    assert conteos["remesas"] == 0
    assert conteos["amortizaciones"] == 0
    assert conteos["devoluciones"] == 0
    assert conteos["asientos"] > 0
    veredicto = export_client.post(
        f"{RUTAS}/{cuerpo['exportacion_id']}/verificar"
    ).json()
    assert veredicto["integro"] is True


# --- Extras del quickstart: autenticacion y permisos -------------------------


def test_quickstart_requiere_autenticacion_y_empresa(export_client) -> None:
    assert export_client.client.post(RUTAS, json={"tipo": "INTEGRAL"}).status_code == 401
    sin_empresa = export_client.client.post(
        RUTAS,
        json={"tipo": "INTEGRAL"},
        headers={"Authorization": f"Bearer {export_client.tokens['admin']}"},
    )
    assert sin_empresa.status_code == 403
    ajena = export_client.client.post(
        RUTAS,
        json={"tipo": "INTEGRAL"},
        headers={
            "Authorization": f"Bearer {export_client.tokens['admin']}",
            "X-Empresa-Activa": "99",
        },
    )
    assert ajena.status_code == 403


@pytest.mark.parametrize("token_key", ["admin", "accountant"])
def test_quickstart_roles_con_permiso_de_crear(export_client, token_key) -> None:
    respuesta = export_client.post(RUTAS, {"tipo": "INTEGRAL"}, token_key=token_key)
    assert respuesta.status_code == 201
    detalle = export_client.get(
        f"{RUTAS}/{respuesta.json()['exportacion_id']}", token_key=token_key
    )
    assert detalle.status_code == 200
