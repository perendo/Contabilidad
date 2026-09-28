"""Constitucion V aplicada a cuentas anuales (SPEC-010 T039/T040).

Precision decimal (4 decimales, nunca float), cuadre de informes, inmutabilidad
del historico de formulaciones y aislamiento multi-tenant estricto.
"""

from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import select

from models.reporting.formulacion import FormulacionCuentasAnuales

IMPORTE = re.compile(r"^-?\d+\.\d{4}$")


def _importes(payload: dict) -> list[str]:
    encontrados: list[str] = []
    for clave, valor in payload.items():
        if isinstance(valor, str) and ("importe" in clave or clave.endswith("total")):
            encontrados.append(valor)
        elif isinstance(valor, dict):
            encontrados.extend(_importes(valor))
        elif isinstance(valor, list):
            for item in valor:
                if isinstance(item, dict):
                    encontrados.extend(_importes(item))
    return encontrados


def test_importes_precision_4_decimales(cuentas_client) -> None:
    fac = cuentas_client
    for recurso in ("balance", "pyg", "efe"):
        data = fac.get(10, f"/api/v1/cuentas-anuales/2026/{recurso}").json()
        for importe in _importes(data):
            assert IMPORTE.match(importe), importe


def test_balance_identidad_exacta(cuentas_client) -> None:
    fac = cuentas_client
    data = fac.get(10, "/api/v1/cuentas-anuales/2026/balance").json()
    assert Decimal(data["total_activo"]) == Decimal(data["total_pasivo"]) + Decimal(
        data["total_patrimonio"]
    )


def test_formulacion_historico_inmutable(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    assert (
        fac.post(
            "/api/v1/cuentas-anuales/2026/formular",
            json={"observaciones": "x"},
        ).status_code
        == 201
    )
    assert (
        fac.post(
            "/api/v1/cuentas-anuales/2026/anular-formulacion",
            json={"motivo": "correccion"},
        ).status_code
        == 200
    )

    async def _primera(session):
        return await session.scalar(
            select(FormulacionCuentasAnuales).where(
                FormulacionCuentasAnuales.empresa_id == 10,
                FormulacionCuentasAnuales.numero_formulacion == 1,
            )
        )

    primera = fac.run(fac.consultar(_primera))
    assert primera is not None
    assert primera.estado.value == "anulada"
    assert primera.snapshot["balance"]["cuadre"] is True
    assert primera.contenido_hash


def test_configuracion_no_contamina_otra_empresa(cuentas_client) -> None:
    fac = cuentas_client
    r = fac.post(
        "/api/v1/cuentas-anuales/configuracion",
        json={
            "ejercicio": 2026,
            "informe_tipo": "BALANCE",
            "agrupaciones": [
                {
                    "agrupacion_codigo": "ANC",
                    "agrupacion_nombre": "Activo No Corriente",
                    "cuenta_ini": "21",
                }
            ],
        },
    )
    assert r.status_code == 200
    b = fac.get(20, "/api/v1/cuentas-anuales/2026/balance").json()
    codigos_b = {
        masa["codigo"]
        for bloque in ("activo", "pasivo", "patrimonio")
        for masa in b[bloque]
    }
    assert "ANC" not in codigos_b


def test_clasificacion_efe_no_afecta_otra_empresa(cuentas_client) -> None:
    fac = cuentas_client
    a = fac.get(10, "/api/v1/cuentas-anuales/2026/efe").json()
    b = fac.get(20, "/api/v1/cuentas-anuales/2026/efe").json()
    assert a["actividades"]["financiacion"]["neto"] == "10000.0000"
    assert b["actividades"]["financiacion"]["neto"] == "2000.0000"