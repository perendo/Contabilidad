"""Verificacion de integridad de la exportacion (SPEC-029 T036, US2).

Quickstart Scenario 2: tras exportar, la huella coincide; si el ZIP se manipula
la verificacion lo detecta. El blob persistido es inmutable (research D9), asi
que re-verificar la exportacion original sigue dando `integro=true` aunque se
haya probado con un ZIP alterado por otro lado.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile

from services.export.verificar import verificar_contenido
from services.export.zip_generator import leer_manifiesto


def _exportar(export_client, **kwargs):
    respuesta = export_client.exportar(**kwargs)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_verificacion_de_una_exportacion_fresca(export_client) -> None:
    cuerpo = _exportar(export_client)
    exportacion_id = cuerpo["exportacion_id"]
    veredicto = export_client.post(f"/api/v1/exportaciones/{exportacion_id}/verificar")
    assert veredicto.status_code == 200, veredicto.text
    datos = veredicto.json()
    assert datos["integro"] is True
    assert datos["diferencias"] == []
    assert datos["sha256_calculado"] == cuerpo["sha256"]
    assert datos["sha256_manifiesto"] == cuerpo["sha256"]
    assert datos["sha256_contenido"] == datos["sha256_contenido_manifiesto"]
    assert datos["exportacion_id"] == exportacion_id
    assert datos["numero_exportacion"] == cuerpo["numero_exportacion"]
    assert len(datos["bloques"]) == cuerpo["n_bloques"]
    assert all(b["coincide"] for b in datos["bloques"])
    for linea in datos["bloques"]:
        assert linea["esperados"] == linea["encontrados"] >= 0


def test_la_huella_manual_coincide_con_la_de_la_api(export_client) -> None:
    """Reproduce el paso manual de `contracts/api-contracts.md`."""
    cuerpo = _exportar(export_client)
    descarga = export_client.get(
        f"/api/v1/exportaciones/{cuerpo['exportacion_id']}/descarga"
    )
    assert hashlib.sha256(descarga.content).hexdigest() == cuerpo["sha256"]
    manifiesto = leer_manifiesto(descarga.content)
    assert manifiesto["sha256_contenido"] == veredicto_hash(descarga.content)
    # El `manifest.json` interior permite verificar sin la API (research D6).
    assert manifiesto["sha256_contenido"] != manifiesto.get("sha256_fichero", "")


def veredicto_hash(contenido: bytes) -> str:
    """Huella del contenido recomputada desde el propio ZIP (autoverificacion)."""
    return verificar_contenido(contenido, 10, None)["sha256_contenido"]


def test_el_blob_es_inmutable_entre_descargas(export_client) -> None:
    exportacion_id = _exportar(export_client)["exportacion_id"]
    primera = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    segunda = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    assert primera.content == segunda.content
    assert hashlib.sha256(primera.content).hexdigest() == hashlib.sha256(
        segunda.content
    ).hexdigest()


def test_manipular_el_zip_se_detecta(export_client) -> None:
    """T036: un ZIP alterado da `integro=false` con diferencias."""
    exportacion_id = _exportar(export_client)["exportacion_id"]
    original = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga"
    ).content
    alterado = bytearray(original)
    alterado[len(alterado) // 2] ^= 0xFF
    veredicto = verificar_contenido(
        bytes(alterado), 10, hashlib.sha256(original).hexdigest()
    )
    assert veredicto["integro"] is False
    assert veredicto["diferencias"]


def test_manipular_un_bloque_concreto_lo_identifica(export_client) -> None:
    exportacion_id = _exportar(export_client)["exportacion_id"]
    original = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga"
    ).content
    manifiesto = leer_manifiesto(original)
    entradas = {ruta: _leer(original, ruta) for ruta in _rutas(original)}
    ruta_bloque = "bloques/003_asientos.json"
    payload = json.loads(entradas[ruta_bloque].decode("utf-8"))
    payload["registros"] = []
    entradas[ruta_bloque] = json.dumps(payload).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archivo:
        for ruta in sorted(entradas):
            archivo.writestr(ruta, entradas[ruta])
    veredicto = verificar_contenido(
        buffer.getvalue(), 10, manifiesto.get("sha256_fichero")
    )
    assert veredicto["integro"] is False
    diferencias = [d for d in veredicto["diferencias"] if d.get("bloque") == "asientos"]
    assert diferencias
    assert veredicto["sha256_manifiesto"] is None  # el manifiesto interior no lleva la huella global


def test_reverificar_tras_manipular_sigue_integro(export_client) -> None:
    """El blob no cambia: la exportacion original permanece integra."""
    cuerpo = _exportar(export_client)
    exportacion_id = cuerpo["exportacion_id"]
    original = export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga"
    ).content
    alterado = bytes(bytearray(original)[:-1]) + bytes([original[-1] ^ 0x01])
    assert (
        verificar_contenido(alterado, 10, cuerpo["sha256"])["integro"] is False
    )
    veredicto = export_client.post(
        f"/api/v1/exportaciones/{exportacion_id}/verificar"
    ).json()
    assert veredicto["integro"] is True
    assert export_client.get(
        f"/api/v1/exportaciones/{exportacion_id}/descarga"
    ).content == original


def test_verificacion_cross_tenant_da_404(export_client) -> None:
    exportacion_id = _exportar(export_client, empresa_id=10)["exportacion_id"]
    assert (
        export_client.post(
            f"/api/v1/exportaciones/{exportacion_id}/verificar", empresa_id=20
        ).status_code
        == 404
    )


def test_verificacion_de_inexistente_da_404(export_client) -> None:
    respuesta = export_client.post(f"/api/v1/exportaciones/{uuid.uuid4()}/verificar")
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "exportacion_no_encontrada"


def test_exportacion_sin_manifiesto_no_es_descargable_ni_verificable(export_client) -> None:
    """Una cabecera `en_proceso` (sin blob) responde 409 en ambos endpoints."""
    from datetime import datetime, timezone

    from models.export.exportacion import EstadoExportacion, Exportacion

    identificador = uuid.uuid4()

    async def _crear(sesion):
        sesion.add(
            Exportacion(
                id=identificador,
                empresa_id=10,
                anio_creacion=2026,
                numero_exportacion=98,
                tipo="INTEGRAL",
                estado=EstadoExportacion.en_proceso,
                created_at=datetime.now(timezone.utc),
            )
        )
        await sesion.flush()

    export_client.run(export_client.mutar(_crear))
    assert (
        export_client.get(f"/api/v1/exportaciones/{identificador}/descarga").status_code
        == 409
    )
    assert (
        export_client.post(f"/api/v1/exportaciones/{identificador}/verificar").status_code
        == 409
    )


def test_cada_verificacion_queda_auditada(export_client) -> None:
    from sqlalchemy import func, select

    from models.audit.audit_log import AuditLog

    exportacion_id = _exportar(export_client)["exportacion_id"]
    for _ in range(3):
        export_client.post(f"/api/v1/exportaciones/{exportacion_id}/verificar")

    async def _op(sesion):
        return await sesion.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.operacion == "VERIFICAR_EXPORTACION",
                AuditLog.entidad_id == exportacion_id,
            )
        )

    assert export_client.run(export_client.consultar(_op)) == 3


def test_verificar_tipo_sii_sobre_exportacion_integral_da_422(export_client) -> None:
    exportacion_id = _exportar(export_client)["exportacion_id"]
    respuesta = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/sii")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "exportacion_no_sii"


def _rutas(contenido: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        return list(archivo.namelist())


def _leer(contenido: bytes, ruta: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        return archivo.read(ruta)
