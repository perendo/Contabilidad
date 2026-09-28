"""Tests SPEC-004 US4 (T040): correlatividad de facturas por empresa/ejercicio."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.invoice import InvoiceTipo
from services.invoicing.invoice_service import crear_factura
from services.invoicing.sequence_factura import existe_numero_factura
from tests.conftest import crear_empresa


async def test_tres_facturas_numeros_1_2_3(db_session: AsyncSession) -> None:
    await crear_empresa(db_session, 10, nif="T00000010", razon_social="Empresa 10 SL")
    await db_session.flush()
    numeros = []
    for _ in range(3):
        factura = await crear_factura(
            db_session, empresa_id=10, tipo=InvoiceTipo.emitida, ejercicio=2026,
            nif_tercero="B12345678", fecha=date(2026, 3, 15),
            base="10.0000", cuota_iva="2.1000", actor="test",
        )
        numeros.append(factura.numero_seq)
    assert numeros == [1, 2, 3]


async def test_ejercicio_distinto_secuencia_independiente(db_session: AsyncSession) -> None:
    await crear_empresa(db_session, 10, nif="T00000010", razon_social="Empresa 10 SL")
    await db_session.flush()
    for ejercicio, esperado in ((2026, 1), (2027, 1), (2026, 2)):
        factura = await crear_factura(
            db_session, empresa_id=10, tipo=InvoiceTipo.recibida, ejercicio=ejercicio,
            nif_tercero="B12345678", fecha=date(ejercicio, 3, 15),
            base="10.0000", cuota_iva="2.1000", actor="test",
        )
        assert factura.numero_seq == esperado
    assert await existe_numero_factura(db_session, 10, 2026, 2) is True
    assert await existe_numero_factura(db_session, 10, 2026, 9) is False
