"""Estructura determinista del ZIP de exportacion (SPEC-029 T013).

Contrato `contracts/export-layout.md` 1 y 5: `manifest.json` en la raiz, un
fichero JSON por bloque con prefijo numerico, orden alfabetico de rutas y
**reproducibilidad byte a byte** para el mismo estado.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from services.export.bloques import BLOQUES_OBLIGATORIOS, Bloque
from services.export.recopilar import BloqueRecopilado
from services.export.zip_generator import (
    FECHA_ZIP,
    MANIFIESTO,
    escribir_zip,
    leer_manifiesto,
    rutas_zip,
)

FECHA = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _recopilado(nombre: str, fichero: str, filas: list[dict]) -> BloqueRecopilado:
    return BloqueRecopilado(
        bloque=Bloque(nombre=nombre, fichero=fichero, descripcion="Zip layout", tablas=()),
        registros=filas,
        conteo_registros=len(filas),
        ejercicio_min=2025,
        ejercicio_max=2026,
    )


def _zip_minimo() -> bytes:
    return escribir_zip(
        42,
        [
            _recopilado("asientos", "003_asientos.json", [{"id": "a", "debe": "1.0000"}]),
            _recopilado("plan_cuentas", "001_plan_cuentas.json", [{"code": "4300"}]),
        ],
        fecha_generacion=FECHA,
    ).contenido


def test_manifest_json_esta_en_la_raiz() -> None:
    contenido = _zip_minimo()
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        nombres = archivo.namelist()
    assert MANIFIESTO in nombres
    assert MANIFIESTO.startswith("/") is False
    assert "bloques/003_asientos.json" in nombres
    assert "bloques/001_plan_cuentas.json" in nombres


def test_orden_de_rutas_es_alfabetico() -> None:
    contenido = _zip_minimo()
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        nombres = archivo.namelist()
    assert nombres == sorted(nombres)
    assert rutas_zip(contenido) == nombres


def test_compresion_deflate_y_entradas_deterministas() -> None:
    contenido = _zip_minimo()
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        for info in archivo.infolist():
            assert info.compress_type == zipfile.ZIP_DEFLATED
            assert info.date_time == FECHA_ZIP
            assert info.create_system == 3
    # El manifiesto va sin comprimir tipo variable, pero el conjunto es deflate.
    assert contenido[:2] == b"PK"


def test_binario_reproducible_para_el_mismo_estado() -> None:
    primero = escribir_zip(
        42,
        [_recopilado("asientos", "003_asientos.json", [{"id": "a", "debe": "1.0000"}])],
        fecha_generacion=FECHA,
    )
    segundo = escribir_zip(
        42,
        [_recopilado("asientos", "003_asientos.json", [{"id": "a", "debe": "1.0000"}])],
        fecha_generacion=FECHA,
    )
    assert primero.contenido == segundo.contenido
    assert primero.sha256 == segundo.sha256
    assert primero.sha256_contenido == segundo.sha256_contenido


def test_cambio_de_fecha_cambia_la_huella_del_fichero() -> None:
    base = escribir_zip(
        42,
        [_recopilado("asientos", "003_asientos.json", [{"id": "a"}])],
        fecha_generacion=FECHA,
    )
    otro = escribir_zip(
        42,
        [_recopilado("asientos", "003_asientos.json", [{"id": "a"}])],
        fecha_generacion=datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc),
    )
    assert base.sha256 != otro.sha256
    # El contenido de los bloques no cambia: solo cambia la cabecera.
    assert base.sha256_contenido == otro.sha256_contenido


def test_zip_de_exportacion_real_tiene_los_17_bloques(export_client) -> None:
    respuesta = export_client.exportar()
    assert respuesta.status_code == 201, respuesta.text
    exportacion_id = respuesta.json()["exportacion_id"]
    descarga = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    assert descarga.status_code == 200
    assert descarga.headers["content-type"] == "application/zip"
    assert 'filename="export_10_1_' in descarga.headers["content-disposition"]
    contenido = descarga.content
    rutas = rutas_zip(contenido)
    assert MANIFIESTO in rutas
    esperados = {bloque.ruta for bloque in BLOQUES_OBLIGATORIOS}
    assert esperados <= set(rutas)
    assert rutas == sorted(rutas)
    manifiesto = leer_manifiesto(contenido)
    # Empresa 10 esta obligada al SII (T043), asi que se anaden los dos ficheros
    # de `datos_sii/` a los 17 bloques obligatorios.
    assert len(manifiesto["bloques"]) == 19
    assert manifiesto["n_bloques"] == 19
    assert "bloques/datos_sii/facturas_emitidas.json" in rutas
    assert "bloques/datos_sii/facturas_recibidas.json" in rutas
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        for bloque in BLOQUES_OBLIGATORIOS:
            payload = json.loads(archivo.read(bloque.ruta).decode("utf-8"))
            assert payload["bloque"] == bloque.nombre
            assert payload["entidades_exportadas"] == list(bloque.entidades)


def test_zip_de_empresa_sin_sii_tiene_solo_los_17_bloques(export_client) -> None:
    """Empresa 20 no tiene `ConfigSii.obligado_sii`: no se anade el bloque SII."""
    respuesta = export_client.exportar(empresa_id=20)
    exportacion_id = respuesta.json()["exportacion_id"]
    contenido = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga", empresa_id=20
    ).content
    manifiesto = leer_manifiesto(contenido)
    assert len(manifiesto["bloques"]) == 17
    assert not any("datos_sii" in ruta for ruta in rutas_zip(contenido))
