"""Principios de la constitución aplicados a facturación (SPEC-007 T030/T039/T050):
partida doble, inmutabilidad de asientos POSTED y aislamiento multi-tenant."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry
from models.invoice.factura import Factura
from models.invoice.factura_linea import FacturaLinea
from models.invoice.serie_factura import SerieFactura


def _emitida(fac, empresa_id: int = 10, **kwargs):
    factura_id = fac.crear(empresa_id=empresa_id, **kwargs).json()["id"]
    r = fac.emitir(factura_id, empresa_id=empresa_id)
    assert r.status_code == 200, r.text
    return factura_id, r.json()


def test_todo_asiento_cuadra(facturacion_client) -> None:
    fac = facturacion_client
    _, venta = _emitida(fac, tipo="VENTA")
    _, compra = _emitida(fac, tipo="COMPRA")
    original_id, _ = _emitida(fac)
    abono = fac.rectificar(original_id).json()

    for asiento_id in (venta["asiento_id"], compra["asiento_id"], abono["asiento_id"]):
        asiento = fac.asiento(asiento_id).json()
        assert asiento["total_debe"] == asiento["total_haber"]
        assert asiento["estado"] == "POSTED"


def test_asiento_posted_no_se_actualiza(facturacion_client) -> None:
    fac = facturacion_client
    _, factura = _emitida(fac)

    async def _update(session):
        await session.execute(
            text("UPDATE journal_entry SET concepto = 'HACK' WHERE id = :id"),
            {"id": uuid.UUID(factura["asiento_id"]).hex},
        )
        await session.flush()

    with pytest.raises(IntegrityError) as exc:
        fac.run(fac.mutar(_update))
    assert "inmutable" in str(exc.value)


def test_asiento_posted_no_se_borra(facturacion_client) -> None:
    fac = facturacion_client
    _, factura = _emitida(fac)

    async def _delete(session):
        await session.execute(
            text("DELETE FROM journal_entry WHERE id = :id"),
            {"id": uuid.UUID(factura["asiento_id"]).hex},
        )
        await session.flush()

    with pytest.raises(IntegrityError) as exc:
        fac.run(fac.mutar(_delete))
    assert "inmutable" in str(exc.value)


def test_emision_no_afecta_a_otra_empresa(facturacion_client) -> None:
    fac = facturacion_client

    async def _contar(session):
        return int(
            await session.scalar(
                select(func.count())
                .select_from(JournalEntry)
                .where(JournalEntry.empresa_id == 20)
            )
            or 0
        )

    _emitida(fac, empresa_id=10)
    assert fac.run(fac.consultar(_contar)) == 0


def test_facturacion_aislada_por_empresa(facturacion_client) -> None:
    fac = facturacion_client
    factura_id, _ = _emitida(fac, empresa_id=10)

    async def _comprobar(session):
        factura = await session.scalar(select(Factura).where(Factura.id == uuid.UUID(factura_id)))
        assert factura is not None
        assert factura.empresa_id == 10

        otras_facturas = await session.scalar(
            select(func.count())
            .select_from(Factura)
            .where(Factura.empresa_id == 20)
        )
        lineas_b = await session.scalar(
            select(func.count())
            .select_from(FacturaLinea)
            .where(FacturaLinea.empresa_id == 20)
        )
        series_b = await session.scalar(
            select(func.count())
            .select_from(SerieFactura)
            .where(SerieFactura.empresa_id == 20)
        )
        return otras_facturas, lineas_b, series_b

    otras_facturas, lineas_b, series_b = fac.run(fac.consultar(_comprobar))
    assert otras_facturas == 0
    assert lineas_b == 0
    assert series_b == 1