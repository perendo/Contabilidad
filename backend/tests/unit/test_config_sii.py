"""Configuracion SII y bloque de datos AEAT (SPEC-029 T038).

Parte 1 (T038): los registros del bloque SII llevan todos los campos que exige
la AEAT, tal y como se listan en `contracts/export-layout.md` 4.
"""

from __future__ import annotations

import json

import pytest

from models.export.config_sii import ConfigSii
from services.export import sii as sii_svc

CAMPOS_AEAT = (
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
)


def test_campos_exigidos_por_el_sii_estan_todos() -> None:
    assert set(CAMPOS_AEAT) == {
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


def test_registros_sii_por_api_cumplen_el_contrato(export_client) -> None:
    respuesta = export_client.exportar(tipo="SII")
    exportacion_id = respuesta.json()["exportacion_id"]
    payload = export_client.get(f"/api/v1/exportaciones/{exportacion_id}/sii").json()
    assert payload["config"]["obligado_sii"] is True
    assert payload["config"]["clave_regimen"] == "01"
    assert payload["config"]["sin_anexo"] is False
    nombres = {b["nombre"] for b in payload["bloques_sii"]}
    assert nombres == {"facturas_emitidas", "facturas_recibidas"}
    emitidas = next(b for b in payload["bloques_sii"] if b["nombre"] == "facturas_emitidas")
    assert emitidas["conteo"] == len(emitidas["registros"]) >= 1
    for registro in emitidas["registros"]:
        for campo in CAMPOS_AEAT:
            assert campo in registro, f"falta {campo}"
        assert registro["TipoFactura"] == "F1"
        assert registro["Naturaleza"] == "VENTA"
        assert registro["FechaOperacion"].count("-") == 2
        assert registro["NumeroFactura"].startswith("F10-")


def test_registros_sii_en_el_zip_cumplen_el_contrato(export_client) -> None:
    respuesta = export_client.exportar(tipo="SII")
    exportacion_id = respuesta.json()["exportacion_id"]
    ficheros = export_client.abrir(
        export_client.get(f"/api/v1/exportaciones/{exportacion_id}/descarga")
    )
    for nombre in ("facturas_emitidas", "facturas_recibidas"):
        payload = json.loads(
            ficheros[f"bloques/datos_sii/{nombre}.json"].decode("utf-8")
        )
        assert payload["bloque"] == f"datos_sii.{nombre}"
        assert payload["conteo_registros"] == len(payload["registros"])
        assert payload["clave_regimen"] == "01"
        assert payload["sin_anexo"] is False
        for registro in payload["registros"]:
            assert set(CAMPOS_AEAT) <= set(registro)


def test_config_efectiva_sin_alta_devuelve_valores_por_defecto(export_client) -> None:
    async def _op(sesion):
        return await sii_svc.config_efectiva(sesion, 20)

    config = export_client.run(export_client.consultar(_op))
    assert config.obligado_sii is False
    assert config.clave_regimen == "01"
    assert config.contrato()["obligado_sii"] is False


def test_config_efectiva_usa_config_sii_de_la_empresa(export_client) -> None:
    async def _op(sesion):
        return await sii_svc.config_efectiva(sesion, 10)

    config = export_client.run(export_client.consultar(_op))
    assert config.obligado_sii is True
    assert config.clave_regimen == "01"
    assert config.fecha_alta == "2025-01-01"


def test_config_efectiva_cae_a_configuracion_sii_de_spec_012(export_client) -> None:
    """Respaldo: si no hay `ConfigSii`, se lee `ConfiguracionSII.obligatorio`."""
    from models.fiscal.configuracion_sii import ConfiguracionSII

    async def _op(sesion):
        sesion.add(
            ConfiguracionSII(empresa_id=20, habilitado=True, obligatorio=True)
        )
        await sesion.flush()
        return await sii_svc.config_efectiva(sesion, 20)

    config = export_client.run(export_client.mutar(_op))
    assert config.obligado_sii is True
    assert config.clave_regimen == "01"


def test_entradas_sii_rechaza_empresa_no_obligada(export_client) -> None:
    from services.export.errores import ExportError

    async def _op(sesion):
        with pytest.raises(ExportError) as info:
            await sii_svc.entradas_sii(sesion, 20)
        return info.value

    exc = export_client.run(export_client.consultar(_op))
    assert exc.code == "sin_configuracion_sii"
    assert exc.status_code == 422


def test_config_sii_se_puede_guardar_por_api(export_client) -> None:
    respuesta = export_client.put("/api/v1/exportaciones/sii/config", {"clave_regimen": "02"})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["clave_regimen"] == "02"
    leido = export_client.get("/api/v1/exportaciones/sii/config")
    assert leido.json()["clave_regimen"] == "02"
    assert leido.json()["obligado_sii"] is False


def test_config_sii_queda_persistida(export_client) -> None:
    export_client.put(
        "/api/v1/exportaciones/sii/config", {"obligado_sii": True, "clave_regimen": "01"}
    )

    async def _op(sesion):
        from sqlalchemy import select

        fila = await sesion.scalar(select(ConfigSii).where(ConfigSii.empresa_id == 10))
        return fila.obligado_sii if fila else None

    assert export_client.run(export_client.consultar(_op)) is True
