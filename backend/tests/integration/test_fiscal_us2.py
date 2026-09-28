"""Tests de integracion US2 del modelo 303 (SPEC-012)."""

from __future__ import annotations


def _m303(fac, empresa_id=10, **params):
    return fac.get(
        empresa_id,
        "/api/v1/modelos/303",
        ejercicio=2026,
        periodo=1,
        tipo_periodo="TRIMESTRE",
        **params,
    )


def test_303_cuadra_con_libros(fiscal_client) -> None:
    fac = fiscal_client
    r = _m303(fac)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cuadre_libros"] is True
    assert data["devengado"]["21.00"]["base"] == "10000.0000"
    assert data["devengado"]["21.00"]["cuota"] == "2100.0000"
    assert data["deducible"]["21.00"]["cuota"] == "1050.0000"
    assert data["resultado"]["a_ingresar"] == "1050.0000"
    assert data["resultado"]["a_compensar"] == "0.0000"


def test_303_intracomunitarias(fiscal_client) -> None:
    fac = fiscal_client
    fac.facturar(tipo="VENTA", base="4000.0000", tercero_key="intra", iva="0")
    data = _m303(fac).json()
    assert data["intracomunitarias"]["0.00"]["base"] == "4000.0000"
    r = fac.get(
        10, "/api/v1/modelos/349", ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE"
    )
    assert r.status_code == 200, r.text
    assert r.json()["operaciones"][0]["importe"] == "4000.0000"


def test_303_multi_tenant(fiscal_client) -> None:
    fac = fiscal_client
    a = _m303(fac, empresa_id=10).json()
    b = _m303(fac, empresa_id=20).json()
    assert a["resultado"]["a_ingresar"] == "1050.0000"
    assert b["resultado"]["a_ingresar"] == "210.0000"
