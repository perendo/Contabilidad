"""Modelos de Gestión ONG (SPEC-019): unicidades y FK multi-tenant.

Verifica la referencia única de subvención por empresa, la asignación exclusiva
de una subcuenta 570 a una única caja y el aislamiento de las unicidades entre
empresas (constitución III).
"""

from __future__ import annotations

import pytest

from services.ngo.caja import crear_caja
from services.ngo.errores import NgoError
from services.ngo.subvenciones import crear_subvencion


def test_referencia_unica_por_empresa(ngo_client):
    ns = ngo_client
    ns.crear_subvencion(empresa_id=10, importe="1000.0000", referencia="REF-A")
    ns.crear_subvencion(empresa_id=20, importe="2000.0000", referencia="REF-A")

    with pytest.raises(NgoError) as exc:
        ns.crear_subvencion(empresa_id=10, importe="500.0000", referencia="REF-A")
    assert exc.value.code == "referencia_duplicada"


def test_caja_usa_una_unica_subcuenta_570(ngo_client):
    ns = ngo_client

    def _crear(empresa_id, nombre, cuenta):
        return ns.run(
            ns.mutar(
                lambda s: crear_caja(
                    s, empresa_id=empresa_id, nombre=nombre, cuenta_570_id=cuenta, tipo="caja"
                )
            )
        )

    _crear(10, "Caja principal", ns.subcuenta_570(10))
    with pytest.raises(NgoError) as exc:
        _crear(10, "Caja secundaria", ns.subcuenta_570(10))
    assert exc.value.code == "cuenta_570_asignada"

    _crear(20, "Caja B", ns.subcuenta_570(20))
    with pytest.raises(NgoError) as exc2:
        _crear(20, "Caja B2", ns.subcuenta_570(20))
    assert exc2.value.code == "cuenta_570_asignada"

    assert crear_caja is not None and crear_subvencion is not None