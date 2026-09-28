"""Tests de integracion US1 de cuentas anuales (SPEC-010): Balance de Situacion."""

from __future__ import annotations

from decimal import Decimal


def _balance(fac, empresa_id=10, **params):
    r = fac.get(empresa_id, "/api/v1/cuentas-anuales/2026/balance", **params)
    return r


def test_balance_cuadra(cuentas_client) -> None:
    fac = cuentas_client
    r = _balance(fac)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cuadre"] is True
    total_activo = Decimal(data["total_activo"])
    total_pp = Decimal(data["total_pasivo"]) + Decimal(data["total_patrimonio"])
    assert total_activo == total_pp == Decimal("13000.0000")


def test_balance_excluye_grupos_6_7(cuentas_client) -> None:
    fac = cuentas_client
    data = _balance(fac).json()
    cuentas = [
        c
        for bloque in ("activo", "pasivo", "patrimonio")
        for masa in data[bloque]
        for partida in masa["partidas"]
        for c in partida["cuentas"]
    ]
    assert not any(c[:1] in ("6", "7") for c in cuentas)
    assert data["resultado_ejercicio"] == "3000.0000"


def test_balance_sin_config_usa_otros(cuentas_client) -> None:
    fac = cuentas_client
    data = _balance(fac).json()
    codigos = {
        masa["codigo"]
        for bloque in ("activo", "pasivo", "patrimonio")
        for masa in data[bloque]
    }
    assert "OTROS" in codigos
    assert data["hay_cuentas_sin_agrupar"] is True


def test_configuracion_agrupa_balance(cuentas_client) -> None:
    fac = cuentas_client
    body = {
        "ejercicio": 2026,
        "informe_tipo": "BALANCE",
        "agrupaciones": [
            {
                "agrupacion_codigo": "ANC",
                "agrupacion_nombre": "Activo No Corriente",
                "cuenta_ini": "21",
            },
            {
                "agrupacion_codigo": "TRE",
                "agrupacion_nombre": "Tesoria",
                "cuenta_ini": "57",
            },
        ],
    }
    r = fac.post("/api/v1/cuentas-anuales/configuracion", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["configuraciones_creadas"] == 2

    data = _balance(fac).json()
    activo = {m["codigo"] for m in data["activo"]}
    assert {"ANC", "TRE"} <= activo


def test_balance_multi_tenant(cuentas_client) -> None:
    fac = cuentas_client
    a = _balance(fac, empresa_id=10).json()
    b = _balance(fac, empresa_id=20).json()
    assert a["total_activo"] == "13000.0000"
    assert b["total_activo"] == "2800.0000"
    assert a["total_activo"] != b["total_activo"]


def test_balance_oficial_requiere_cierre(cuentas_client) -> None:
    fac = cuentas_client
    r = _balance(fac, modo="oficial")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ejercicio_no_cerrado"


def test_balance_comparativo(cuentas_client) -> None:
    fac = cuentas_client
    fac.asiento(
        10,
        [
            {"cuenta": "5720", "debe": "400.0000", "haber": "0", "detalle": "a"},
            {"cuenta": "1110", "debe": "0", "haber": "400.0000", "detalle": "b"},
        ],
        "2025-06-01",
        "Aportacion 2025",
    )
    data = _balance(fac, comparativo="true").json()
    assert data["comparativo_anterior"] is not None
    assert data["comparativo_anterior"]["ejercicio"] == 2025