"""Tests de integracion US2 de cuentas anuales (SPEC-010): Perdidas y Ganancias."""

from __future__ import annotations

from decimal import Decimal


def _pyg(fac, empresa_id=10, **params):
    return fac.get(empresa_id, "/api/v1/cuentas-anuales/2026/pyg", **params)


def test_pyg_resultado(cuentas_client) -> None:
    fac = cuentas_client
    r = _pyg(fac)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_ingresos"] == "5000.0000"
    assert data["total_gastos"] == "2000.0000"
    assert data["resultado_ejercicio"] == "3000.0000"
    assert Decimal(data["resultado_ejercicio"]) == Decimal(data["total_ingresos"]) - Decimal(
        data["total_gastos"]
    )


def test_pyg_sin_cierre_no_coincide(cuentas_client) -> None:
    fac = cuentas_client
    data = _pyg(fac).json()
    assert data["coincide_cierre"] is False
    assert data["descuadre_cierre"] is True


def test_pyg_coincide_tras_cierre(cuentas_client) -> None:
    fac = cuentas_client
    assert fac.cerrar(empresa_id=10, year=2026)["is_closed"] is True
    data = _pyg(fac).json()
    assert data["resultado_ejercicio"] == "3000.0000"
    assert data["resultado_cierre"] == "3000.0000"
    assert data["coincide_cierre"] is True


def test_pyg_oficial_sin_cierre_409(cuentas_client) -> None:
    fac = cuentas_client
    r = _pyg(fac, modo="oficial")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "descuadre_cierre"


def test_pyg_multi_tenant(cuentas_client) -> None:
    fac = cuentas_client
    a = _pyg(fac, empresa_id=10).json()
    b = _pyg(fac, empresa_id=20).json()
    assert a["resultado_ejercicio"] == "3000.0000"
    assert b["resultado_ejercicio"] == "800.0000"