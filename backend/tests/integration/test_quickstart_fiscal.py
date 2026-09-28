"""Escenarios del quickstart fiscal (SPEC-012 T052)."""

from __future__ import annotations


def _get(fac, empresa_id, ruta, **params):
    return fac.get(empresa_id, ruta, **params)


def test_scenario_1_libro_emitidas(fiscal_client) -> None:
    fac = fiscal_client
    data = _get(
        fac, 10, "/api/v1/libros-iva/emitidas",
        ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE",
    ).json()
    assert data["total_cuota"] == "2100.0000"
    b = _get(
        fac, 20, "/api/v1/libros-iva/emitidas",
        ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE",
    ).json()
    assert b["total_cuota"] == "420.0000"


def test_scenario_2_303(fiscal_client) -> None:
    fac = fiscal_client
    data = _get(
        fac, 10, "/api/v1/modelos/303",
        ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE",
    ).json()
    assert data["cuadre_libros"] is True
    assert data["resultado"]["a_ingresar"] == "1050.0000"


def test_scenario_3_exportacion(fiscal_client) -> None:
    fac = fiscal_client
    r = fac.post(
        "/api/v1/fiscal/exportaciones",
        json={"modelo": "303", "ejercicio": 2026, "periodo": 1, "formato": "csv"},
    )
    assert r.status_code == 201
    assert r.json()["numero_exportacion"] == 1
    segunda = fac.post(
        "/api/v1/fiscal/exportaciones",
        json={"modelo": "303", "ejercicio": 2026, "periodo": 1, "formato": "csv"},
    )
    assert segunda.json()["advertencia"] == "re-exportado"


def test_scenario_4_recargo(fiscal_client) -> None:
    fac = fiscal_client
    fac.facturar(tipo="VENTA", base="1000.0000", recargo="5.2")
    data = _get(
        fac, 10, "/api/v1/modelos/303",
        ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE",
    ).json()
    assert data["recargo_equivalencia"]["cuota"] == "52.0000"


def test_scenario_6_347_349(fiscal_client) -> None:
    fac = fiscal_client
    fac.facturar(tipo="VENTA", base="4000.0000", tercero_key="intra", iva="0")
    m347 = _get(fac, 10, "/api/v1/modelos/347", ejercicio=2026).json()
    assert m347["total_general"] != "0.0000"
    m349 = _get(
        fac, 10, "/api/v1/modelos/349",
        ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE",
    ).json()
    assert m349["total_general"] == "4000.0000"


def test_scenario_7_sii_y_aislamiento(fiscal_client) -> None:
    fac = fiscal_client
    assert _get(fac, 10, "/api/v1/sii/configuracion").json()["habilitado"] is False
    r = fac.post(
        "/api/v1/sii/configuracion",
        json={"habilitado": True, "identificador_emisor": "B00000010"},
    )
    assert r.json()["periodicidad_303"] == "MES"
    assert _get(fac, 20, "/api/v1/sii/configuracion").json()["habilitado"] is False