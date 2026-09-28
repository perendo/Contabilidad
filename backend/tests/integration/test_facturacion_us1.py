"""Tests de integración US1 de facturación (SPEC-007): borrador, emisión,
impuestos, numeración correlativa, multi-tenant y ejercicio cerrado."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry


async def _contar_asientos(session, empresa_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(JournalEntry.empresa_id == empresa_id)
        )
        or 0
    )


def test_borrador_no_contabiliza(facturacion_client) -> None:
    fac = facturacion_client
    r = fac.crear()
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["estado"] == "borrador"
    assert data["numero"] is None
    assert data["asiento_id"] is None
    assert data["importe_total"] == "121.0000"

    detalle = fac.detalle(data["id"]).json()
    assert detalle["asiento"] is None
    assert fac.run(fac.consultar(lambda s: _contar_asientos(s, 10))) == 0


def test_emitir_genera_asiento_balanceado(facturacion_client) -> None:
    fac = facturacion_client
    factura_id = fac.crear().json()["id"]
    r = fac.emitir(factura_id)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["estado"] == "emitida"
    assert data["numero"] == "S101"
    assert data["numero_int"] == 1
    assert data["asiento_id"]

    asiento = fac.asiento(data["asiento_id"]).json()
    assert asiento["estado"] == "POSTED"
    assert asiento["total_debe"] == asiento["total_haber"] == "121.0000"
    cuentas = {l["cuenta"]: l for l in asiento["lineas"]}
    assert cuentas["4300"]["debe"] == "121.0000"
    assert cuentas["7000"]["haber"] == "100.0000"
    assert cuentas["4770"]["haber"] == "21.0000"


def test_irpf_reduce_total(facturacion_client) -> None:
    fac = facturacion_client
    linea = fac.linea(tipo_irpf="15", base_irpf="100.0000")
    data = fac.crear(lineas=[linea]).json()
    assert data["importe_irpf"] == "15.0000"
    assert data["importe_total"] == "106.0000"


def test_irpf_usa_cuenta_4751(facturacion_client) -> None:
    fac = facturacion_client
    linea = fac.linea(tipo_irpf="15", base_irpf="100.0000")
    factura_id = fac.crear(lineas=[linea]).json()["id"]
    emitida = fac.emitir(factura_id)
    assert emitida.status_code == 200, emitida.text
    cuentas = {
        linea["cuenta"]
        for linea in fac.asiento(emitida.json()["asiento_id"]).json()["lineas"]
    }
    assert "4751" in cuentas
    assert "4750" not in cuentas


def test_descuento_por_linea(facturacion_client) -> None:
    fac = facturacion_client
    data = fac.crear(lineas=[fac.linea(descuento="10")]).json()
    assert data["importe_base"] == "90.0000"
    assert data["importe_iva"] == "18.9000"
    assert data["importe_total"] == "108.9000"


def test_recargo_equivalencia_cuenta_separada(facturacion_client) -> None:
    fac = facturacion_client
    factura_id = fac.crear(lineas=[fac.linea(tipo_recargo="5.2")]).json()["id"]
    r = fac.emitir(factura_id)
    assert r.status_code == 200, r.text
    asiento = fac.asiento(r.json()["asiento_id"]).json()
    cuentas = {l["cuenta"]: l for l in asiento["lineas"]}
    assert cuentas["4770"]["haber"] == "21.0000"
    assert cuentas["4772"]["haber"] == "5.2000"


def test_compra_asiento_invertido(facturacion_client) -> None:
    fac = facturacion_client
    factura_id = fac.crear(tipo="COMPRA").json()["id"]
    r = fac.emitir(factura_id)
    assert r.status_code == 200, r.text
    asiento = fac.asiento(r.json()["asiento_id"]).json()
    cuentas = {l["cuenta"]: l for l in asiento["lineas"]}
    assert cuentas["6000"]["debe"] == "100.0000"
    assert cuentas["4720"]["debe"] == "21.0000"
    assert cuentas["4100"]["haber"] == "121.0000"


def test_numeracion_correlativa_por_serie(facturacion_client) -> None:
    fac = facturacion_client
    id1 = fac.crear().json()["id"]
    id2 = fac.crear().json()["id"]
    assert fac.emitir(id1).json()["numero"] == "S101"
    assert fac.emitir(id2).json()["numero"] == "S102"

    serie_r = fac.crear_serie(codigo="R", prefijo="R").json()["id"]
    id3 = fac.crear(serie_id=serie_r).json()["id"]
    assert fac.emitir(id3).json()["numero"] == "R1"


def test_numeracion_independiente_por_ejercicio(facturacion_client) -> None:
    fac = facturacion_client
    id26 = fac.crear(fecha="2026-06-01", ejercicio=2026).json()["id"]
    id27 = fac.crear(fecha="2027-06-01", ejercicio=2027).json()["id"]
    assert fac.emitir(id26).json()["numero_int"] == 1
    assert fac.emitir(id27).json()["numero_int"] == 1


def test_ejercicio_cerrado_rechaza_emision(facturacion_client) -> None:
    fac = facturacion_client

    async def _cerrar(session):
        session.add(
            FiscalYear(
                empresa_id=10,
                year=2026,
                date_start=date(2026, 1, 1),
                date_end=date(2026, 12, 31),
                is_closed=True,
            )
        )
        await session.flush()

    fac.run(fac.mutar(_cerrar))
    factura_id = fac.crear().json()["id"]
    r = fac.emitir(factura_id)
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_serie_inactiva_rechaza_emision(facturacion_client) -> None:
    fac = facturacion_client
    serie = fac.crear_serie(codigo="X", prefijo="X").json()["id"]
    assert fac.estado_serie(serie, False).status_code == 200
    factura_id = fac.crear(serie_id=serie).json()["id"]
    r = fac.emitir(factura_id)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "serie_inactiva"


def test_listado_filtra_por_estado(facturacion_client) -> None:
    fac = facturacion_client
    id1 = fac.crear().json()["id"]
    fac.crear()
    fac.emitir(id1)
    assert fac.listar(estado="emitida").json()["total"] == 1
    assert fac.listar(estado="borrador").json()["total"] == 1


def test_multi_tenant_aislado(facturacion_client) -> None:
    fac = facturacion_client
    factura_id = fac.crear().json()["id"]
    assert fac.detalle(factura_id, empresa_id=20).status_code == 404
    assert fac.listar(empresa_id=20).json()["total"] == 0
    assert fac.emitir(factura_id, empresa_id=20).status_code == 404


def test_tercero_de_otra_empresa_rechazado(facturacion_client) -> None:
    fac = facturacion_client
    r = fac.crear(empresa_id=10, tercero_id=fac.terceros[20])
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "tercero_no_encontrado"


def test_tipo_invalido_rechazado(facturacion_client) -> None:
    fac = facturacion_client
    r = fac.crear(tipo="RECTIFICATIVA")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "tipo_invalido"


def test_uuid_empresa_serie_no_contamina(facturacion_client) -> None:
    fac = facturacion_client
    r = fac.crear(serie_id=uuid.uuid4())
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "serie_no_encontrada"