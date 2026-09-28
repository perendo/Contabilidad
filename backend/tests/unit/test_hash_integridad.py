"""Huella SHA-256 e integridad de la exportacion (SPEC-029 T029/T030).

Parte 1 (T029): la huella es estable y coincide con la del manifiesto.
Parte 2 (T030): un byte alterado se detecta (`integro=false` + diferencias).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from services.export.manifiesto import contenido_digest
from services.export.verificar import verificar_contenido
from services.export.zip_generator import escribir_zip, leer_manifiesto
from tests.unit import export_support as soporte

FECHA = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _recopilado(nombre: str, fichero: str, filas: list[dict]):
    return soporte.bloque_de_prueba(nombre, fichero, filas)


def _contenido() -> bytes:
    return escribir_zip(
        42,
        [
            _recopilado("asientos", "003_asientos.json", [{"id": "a"}, {"id": "b"}]),
            _recopilado("plan_cuentas", "001_plan_cuentas.json", [{"code": "4300"}]),
        ],
        fecha_generacion=FECHA,
    ).contenido


# --- Parte 1 · hash coincide (T029) ----------------------------------------


def test_sha256_del_binario_es_estable_y_coincide_con_el_manifiesto() -> None:
    contenido = _contenido()
    primero = hashlib.sha256(contenido).hexdigest()
    segundo = hashlib.sha256(contenido).hexdigest()
    assert primero == segundo
    assert len(primero) == 64
    manifiesto = leer_manifiesto(contenido)
    rutas = {b["bloque"]: f"bloques/{b['fichero']}" for b in manifiesto["bloques"]}
    real: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        for linea in manifiesto["bloques"]:
            ruta = rutas[linea["bloque"]]
            huella = hashlib.sha256(archivo.read(ruta)).hexdigest()
            assert huella == linea["sha256"]
            real[ruta] = huella
    # `sha256_contenido` es recomputable a partir de los ficheros del ZIP.
    assert manifiesto["sha256_contenido"] == contenido_digest(real)
    assert contenido_digest(real) == contenido_digest(real)


def test_verificacion_de_contenido_sobre_zip_intacto() -> None:
    contenido = _contenido()
    huella = hashlib.sha256(contenido).hexdigest()
    veredicto = verificar_contenido(contenido, 42, huella)
    assert veredicto["integro"] is True
    assert veredicto["diferencias"] == []
    assert veredicto["sha256_calculado"] == huella
    assert veredicto["sha256_manifiesto"] == huella
    assert len(veredicto["bloques"]) == 2
    assert all(b["coincide"] for b in veredicto["bloques"])


# --- Parte 2 · deteccion de alteracion (T030) ------------------------------


def test_un_byte_alterado_invalida_la_huella() -> None:
    contenido = bytearray(_contenido())
    contenido[-1] = contenido[-1] ^ 0x01
    alterado = bytes(contenido)
    assert hashlib.sha256(alterado).hexdigest() != hashlib.sha256(_contenido()).hexdigest()
    veredicto = verificar_contenido(alterado, 42, hashlib.sha256(_contenido()).hexdigest())
    assert veredicto["integro"] is False
    tipos = {d["tipo"] for d in veredicto["diferencias"]}
    assert "huella_fichero" in tipos


def test_zip_sin_manifest_json_se_reporta_inconsistente() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archivo:
        archivo.writestr("bloques/001_plan_cuentas.json", "{}")
    veredicto = verificar_contenido(buffer.getvalue(), 42, None)
    assert veredicto["integro"] is False
    assert veredicto["diferencias"][0]["tipo"] == "manifiesto_ausente"


def test_tenant_id_distinto_se_detecta() -> None:
    """Aislar la exportacion de la empresa 42 en la 99 debe fallar (constitution III)."""
    contenido = _contenido()
    veredicto = verificar_contenido(contenido, 99, hashlib.sha256(contenido).hexdigest())
    assert veredicto["integro"] is False
    assert any(d["tipo"] == "tenant" and d["encontrado"] == 42 for d in veredicto["diferencias"])


def test_bloque_manipulado_solo_cambia_su_conteo() -> None:
    """Si se edita el JSON de un bloque, la huella de contenido no cuadra."""
    contenido = _contenido()
    origen = leer_manifiesto(contenido)
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        entradas = {n: archivo.read(n) for n in archivo.namelist()}
    entradas["bloques/003_asientos.json"] = json.dumps(
        {
            "bloque": "asientos",
            "conteo_registros": 5,
            "registros": [{"id": "x"}],
        }
    ).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archivo:
        for ruta in sorted(entradas):
            archivo.writestr(ruta, entradas[ruta])
    alterado = buffer.getvalue()
    veredicto = verificar_contenido(alterado, 42, hashlib.sha256(alterado).hexdigest())
    assert veredicto["integro"] is False
    tipos = {d["tipo"] for d in veredicto["diferencias"]}
    assert "conteo_bloque" in tipos
    bloque = next(b for b in veredicto["bloques"] if b["bloque"] == "asientos")
    assert bloque["esperados"] == 2
    assert bloque["encontrados"] == 5
    assert bloque["coincide"] is False
    assert origen["tenant_id"] == 42


def test_contenido_digest_es_independiente_del_orden_de_insercion() -> None:
    a = {"bloques/001_x.json": "1", "bloques/002_y.json": "2"}
    b = {"bloques/002_y.json": "2", "bloques/001_x.json": "1"}
    assert contenido_digest(a) == contenido_digest(b)
    assert contenido_digest(a) != contenido_digest({"bloques/001_x.json": "9"})
