"""Tests de integracion US4 de regimenes especiales (SPEC-012)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from services.vat.criterio_caja import aplicar_criterio_caja


def _libro_emitidas(fac, empresa_id=10):
    return fac.get(
        empresa_id,
        "/api/v1/libros-iva/emitidas",
        ejercicio=2026,
        periodo=1,
        tipo_periodo="TRIMESTRE",
    ).json()


def _m303(fac, empresa_id=10):
    return fac.get(
        empresa_id,
        "/api/v1/modelos/303",
        ejercicio=2026,
        periodo=1,
        tipo_periodo="TRIMESTRE",
    ).json()


def test_recargo_cuota_separada(fiscal_client) -> None:
    fac = fiscal_client
    fac.facturar(tipo="VENTA", base="1000.0000", recargo="5.2")
    libro = _libro_emitidas(fac)
    op = next(o for o in libro["operaciones"] if o["base"] == "1000.0000")
    assert op["cuota"] == "210.0000"
    assert op["recargo_cuota"] == "52.0000"

    data = _m303(fac)
    assert data["recargo_equivalencia"]["cuota"] == "52.0000"


def test_criterio_caja_diferido_y_liquidacion(fiscal_client) -> None:
    fac = fiscal_client
    fid = fac.facturar(tipo="VENTA", base="1000.0000", regimen_caja=True)
    fac.run(fac.mutar(lambda s: aplicar_criterio_caja(s, empresa_id=10, factura_id=fid)))

    libro = _libro_emitidas(fac)
    op = next(o for o in libro["operaciones"] if o["factura_id"] == str(fid))
    assert op["incluir_303"] is False

    data = _m303(fac)
    assert data["devengado"]["21.00"]["cuota"] == "2100.0000"
    assert data["iva_diferido"]["pendiente"] == "210.0000"

    async def _vencimiento(session):
        session.add(
            Vencimiento(
                empresa_id=10,
                tercero_id=fac.terceros[10]["cliente"],
                factura_id=fid,
                recibo_num="R1",
                iban="ES91000000000000000010",
                ejercicio=2026,
                tipo=TipoVencimiento.cobro,
                fecha_vencimiento=date(2026, 4, 10),
                importe=Decimal("1210.0000"),
                acumulado=Decimal("1210.0000"),
                estado=EstadoVencimiento.cobrado,
            )
        )
        await session.flush()

    fac.run(fac.mutar(_vencimiento))
    sync = fac.post("/api/v1/regimenes/criterio-caja", json={"habilitado": True})
    assert sync.status_code == 200, sync.text
    assert sync.json()["liquidados"] == 1

    tras = _m303(fac)
    assert tras["devengado"]["21.00"]["cuota"] == "2310.0000"
    assert tras["iva_diferido"]["pendiente"] == "0.0000"


def test_regimenes_estado_y_tenant(fiscal_client) -> None:
    fac = fiscal_client
    estado = fac.get(10, "/api/v1/regimenes/estado")
    assert estado.status_code == 200, estado.text
    assert {"recargo_equivalencia", "criterio_caja", "sii"} <= set(estado.json())

    r = fac.post(
        "/api/v1/regimenes/recargo-equivalencia",
        json={"habilitado": True, "cuenta_recargo": "4772"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["habilitado"] is True

    b = fac.get(20, "/api/v1/regimenes/estado").json()
    assert b["recargo_equivalencia"]["habilitado"] is False