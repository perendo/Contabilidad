"""Tests de la interfaz SII (SPEC-012, sin envio)."""

from __future__ import annotations


def test_sii_deshabilitado_por_defecto(fiscal_client) -> None:
    fac = fiscal_client
    r = fac.get(10, "/api/v1/sii/configuracion")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["habilitado"] is False
    assert data["periodicidad_303"] == "TRIMESTRE"


def test_sii_xml_sin_habilitar_409(fiscal_client) -> None:
    fac = fiscal_client
    r = fac.get(
        10,
        "/api/v1/sii/operaciones/emitidas",
        ejercicio=2026,
        periodo=1,
        tipo_periodo="TRIMESTRE",
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "sii_no_habilitado"


def test_sii_habilitar_ajusta_periodicidad(fiscal_client) -> None:
    fac = fiscal_client
    r = fac.post(
        "/api/v1/sii/configuracion",
        json={"habilitado": True, "identificador_emisor": "B00000010"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["habilitado"] is True
    assert r.json()["periodicidad_303"] == "MES"
    assert r.json()["advertencia"] == "periodicidad_ajustada_a_mensual"


def test_sii_genera_xml(fiscal_client) -> None:
    fac = fiscal_client
    fac.post(
        "/api/v1/sii/configuracion",
        json={"habilitado": True, "identificador_emisor": "B00000010"},
    )
    r = fac.get(
        10,
        "/api/v1/sii/operaciones/emitidas",
        ejercicio=2026,
        periodo=1,
        tipo_periodo="MES",
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "<SuministroLF>" in data["xml"]
    assert data["n_operaciones"] == 1
    assert len(data["sha256"]) == 64


def test_sii_multi_tenant(fiscal_client) -> None:
    fac = fiscal_client
    fac.post(
        "/api/v1/sii/configuracion",
        json={"habilitado": True, "identificador_emisor": "B00000010"},
    )
    b = fac.get(20, "/api/v1/sii/configuracion").json()
    assert b["habilitado"] is False