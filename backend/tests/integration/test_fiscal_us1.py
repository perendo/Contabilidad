"""Tests de integracion US1 de libros de IVA (SPEC-012)."""

from __future__ import annotations

from datetime import date

from services.invoicing.emision import crear_factura_borrador


def _libro(fac, tipo, empresa_id=10, **params):
    return fac.get(
        empresa_id,
        f"/api/v1/libros-iva/{tipo}",
        ejercicio=2026,
        periodo=1,
        tipo_periodo="TRIMESTRE",
        **params,
    )


def test_libro_emitidas_deriva_facturas(fiscal_client) -> None:
    fac = fiscal_client
    r = _libro(fac, "emitidas")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_base"] == "10000.0000"
    assert data["total_cuota"] == "2100.0000"
    op = data["operaciones"][0]
    assert op["tipo_iva"] == "21.00"
    assert op["incluir_303"] is True
    assert op["recargo_cuota"] == "0.0000"


def test_libro_recibidas_deriva_facturas(fiscal_client) -> None:
    fac = fiscal_client
    data = _libro(fac, "recibidas").json()
    assert data["total_base"] == "5000.0000"
    assert data["total_cuota"] == "1050.0000"


def test_libro_intracomunitarias_inicial_vacio(fiscal_client) -> None:
    fac = fiscal_client
    data = _libro(fac, "intracomunitarias").json()
    assert data["operaciones"] == []


def test_intracomunitaria_aparece(fiscal_client) -> None:
    fac = fiscal_client
    fac.facturar(tipo="VENTA", base="4000.0000", tercero_key="intra", iva="0")
    data = _libro(fac, "intracomunitarias").json()
    assert len(data["operaciones"]) == 1
    assert data["total_base"] == "4000.0000"
    assert data["total_cuota"] == "0.0000"


def test_factura_sin_asiento_excluida(fiscal_client) -> None:
    fac = fiscal_client

    async def _borrador(session):
        await crear_factura_borrador(
            session,
            empresa_id=10,
            serie_id=fac.series[10],
            ejercicio=2026,
            fecha=date(2026, 1, 15),
            tipo="VENTA",
            tercero_id=fac.terceros[10]["cliente"],
            concepto_global="sin asiento",
            lineas=[
                {
                    "descripcion": "x",
                    "cantidad": "1",
                    "precio_unitario": "7777.0000",
                    "porcentaje_descuento": "0",
                    "tipo_iva": "21",
                    "tipo_recargo": "0",
                    "tipo_irpf": "0",
                    "base_irpf": "0",
                }
            ],
        )

    fac.run(fac.mutar(_borrador))
    data = _libro(fac, "emitidas").json()
    assert data["total_base"] == "10000.0000"


def test_libros_multi_tenant(fiscal_client) -> None:
    fac = fiscal_client
    a = _libro(fac, "emitidas", empresa_id=10).json()
    b = _libro(fac, "emitidas", empresa_id=20).json()
    assert a["total_base"] == "10000.0000"
    assert b["total_base"] == "2000.0000"


def test_tipo_libro_invalido_409(fiscal_client) -> None:
    fac = fiscal_client
    r = fac.get(10, "/api/v1/libros-iva/otro", ejercicio=2026, periodo=1)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "tipo_libro_invalido"